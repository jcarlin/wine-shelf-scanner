"""
Flash Names pipeline: minimal-prompt LLM + parallel Vision API.

Strategy:
1. Fire Gemini Flash (names+ratings prompt) and Vision API concurrently
2. LLM returns wine names + estimated ratings (~2-3s, minimal output tokens)
3. Vision API returns bboxes + OCR (~2-3s)
4. Merge: assign LLM names to Vision bboxes via OCR text similarity
5. Parallel DB lookups for authoritative ratings (DB rating overrides LLM estimate)

Expected latency: 3-5s total (dominated by the slower of LLM/Vision).
"""

import asyncio
import base64
import io
import json
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

from ..config import Config
from ..models.enums import RatingSource, WineSource
from .llm_rating_cache import get_llm_rating_cache, LLMRatingCache
from .ocr_processor import BottleText, OCRProcessor
from .recognition_pipeline import RecognizedWine
from .vision import BoundingBox as VisionBBox, DetectedObject, VisionResult, VisionService
from .wine_matcher import WineMatcher, WineMatch

logger = logging.getLogger(__name__)

# Lazy import for litellm
_litellm = None
_litellm_checked = False


def _get_litellm():
    global _litellm, _litellm_checked
    if not _litellm_checked:
        _litellm_checked = True
        try:
            import litellm
            litellm.set_verbose = False
            _litellm = litellm
        except ModuleNotFoundError:
            _litellm = None
    return _litellm


NAMES_ONLY_PROMPT = """List every wine bottle visible in this photo. For each bottle, return the wine name and the approximate center position of the bottle as x,y fractions (0.0-1.0 range, where 0,0 is top-left).

Return ONLY a JSON array:
[{"name": "Caymus Cabernet Sauvignon", "x": 0.15, "y": 0.45}, {"name": "Opus One 2019", "x": 0.38, "y": 0.44}]

Include the producer/winery and grape variety when readable. For partial text, give your best guess. Return ONLY the JSON array."""

RATING_PROMPT_TEMPLATE = """Estimate the Vivino community rating (1.0-5.0) for each wine. Use ratings that match what you'd find on Vivino — most wines fall between 3.5-4.3, well-known premium wines are 4.3-4.7, and iconic wines are 4.7+. Be specific, not generic.

Wines: {wines}

Return ONLY a JSON object: {{"Wine Name": 4.2, "Other Wine": 3.8}}"""


@dataclass
class FlashNamesResult:
    """Result from the flash names pipeline."""
    recognized_wines: list[RecognizedWine]
    fallback: list  # wines without bboxes
    timings: dict = field(default_factory=dict)


class FlashNamesPipeline:
    """
    Minimal-prompt LLM pipeline with parallel Vision API for bboxes.

    Flow:
    1. [Parallel] Gemini Flash names+ratings + Vision API
    2. OCR grouping from Vision results
    3. Match LLM names to Vision bottles by OCR text similarity
    4. DB lookups for authoritative ratings (overrides LLM estimates)
    5. Unmatched LLM names -> fallback list with LLM-estimated ratings
    """

    def __init__(
        self,
        wine_matcher: Optional[WineMatcher] = None,
        model: Optional[str] = None,
        use_llm_cache: Optional[bool] = None,
    ):
        self.wine_matcher = wine_matcher or WineMatcher()
        self.model = model or f"gemini/{Config.fast_pipeline_model()}"
        self._executor = ThreadPoolExecutor(max_workers=8)
        cache_enabled = use_llm_cache if use_llm_cache is not None else Config.use_llm_cache()
        self._llm_cache: Optional[LLMRatingCache] = get_llm_rating_cache() if cache_enabled else None

    async def scan(self, image_bytes: bytes) -> FlashNamesResult:
        """Run flash names pipeline."""
        timings: dict = {}
        total_start = time.perf_counter()

        # Fire both concurrently
        vision_task = asyncio.get_event_loop().run_in_executor(
            None, self._run_vision, image_bytes
        )
        gemini_task = self._run_gemini_names(image_bytes)

        vision_result, llm_wines = await asyncio.gather(
            vision_task, gemini_task, return_exceptions=True
        )

        leg_end = time.perf_counter()
        timings['parallel_ms'] = round((leg_end - total_start) * 1000)

        # Handle failures
        if isinstance(vision_result, Exception):
            logger.warning(f"FlashNames: Vision API failed: {vision_result}")
            vision_result = None
        if isinstance(llm_wines, Exception):
            logger.warning(f"FlashNames: Gemini failed: {llm_wines}")
            llm_wines = []

        if not llm_wines:
            timings['total_ms'] = round((time.perf_counter() - total_start) * 1000)
            return FlashNamesResult(recognized_wines=[], fallback=[], timings=timings)

        # Extract names and ratings for DB lookup
        llm_names = [w['name'] for w in llm_wines]
        llm_ratings = {w['name']: w.get('rating') for w in llm_wines}

        # DB lookups (parallel)
        t_db = time.perf_counter()
        db_results = self._batch_db_lookup(llm_names)
        timings['db_ms'] = round((time.perf_counter() - t_db) * 1000)

        # Estimate ratings for wines not found in DB
        unmatched_names = [
            name for name in llm_names
            if db_results.get(name) is None  # No DB or cache match
        ]
        if unmatched_names:
            t_rate = time.perf_counter()
            estimated = await self._estimate_ratings(unmatched_names)
            timings['rating_ms'] = round((time.perf_counter() - t_rate) * 1000)
            for name, est_rating in estimated.items():
                llm_ratings[name] = est_rating

        # Last-resort default for any still-unrated wines
        for name in llm_names:
            db_match = db_results.get(name)
            db_rating = db_match.rating if db_match else None
            if db_rating is None and llm_ratings.get(name) is None:
                llm_ratings[name] = 3.5

        # Merge with Vision bboxes if available
        t_merge = time.perf_counter()
        if vision_result and vision_result.objects:
            recognized, fallback = self._merge_with_vision(
                llm_wines, llm_ratings, db_results, vision_result, image_bytes
            )
        else:
            recognized, fallback = self._names_only_results(llm_wines, llm_ratings, db_results)
        timings['merge_ms'] = round((time.perf_counter() - t_merge) * 1000)

        # Cache LLM-discovered wines
        self._cache_results(recognized, fallback)

        timings['total_ms'] = round((time.perf_counter() - total_start) * 1000)
        logger.info(
            f"FlashNames: {len(recognized)} results, {len(fallback)} fallback "
            f"in {timings['total_ms']}ms "
            f"(parallel={timings['parallel_ms']}ms, db={timings['db_ms']}ms, "
            f"merge={timings['merge_ms']}ms)"
        )

        return FlashNamesResult(
            recognized_wines=recognized, fallback=fallback, timings=timings
        )

    def _run_vision(self, image_bytes: bytes) -> VisionResult:
        """Call Google Vision API (synchronous)."""
        t0 = time.perf_counter()
        service = VisionService()
        result = service.analyze(image_bytes)
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info(f"FlashNames: Vision API: {len(result.objects)} objects in {elapsed}ms")
        return result

    @staticmethod
    def _compress_for_llm(image_bytes: bytes, max_dim: int = 1600, quality: int = 75) -> bytes:
        """Compress image for LLM call — smaller than Vision API needs."""
        from PIL import Image as PILImage
        img = PILImage.open(io.BytesIO(image_bytes))
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim))
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality)
        return buf.getvalue()

    async def _run_gemini_names(self, image_bytes: bytes) -> list[dict]:
        """Call Gemini Flash with names-only prompt. Returns list of {name, rating} dicts."""
        litellm = _get_litellm()
        if not litellm:
            logger.error("FlashNames: litellm not available")
            return []

        compressed = self._compress_for_llm(image_bytes)
        image_b64 = base64.b64encode(compressed).decode("utf-8")

        t0 = time.perf_counter()
        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                        {"type": "text", "text": NAMES_ONLY_PROMPT},
                    ],
                }],
                max_tokens=500,
                temperature=0.1,
            )
            elapsed = round((time.perf_counter() - t0) * 1000)
            text = response.choices[0].message.content.strip()

            # Strip markdown code blocks
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            parsed = json.loads(text)
            if not isinstance(parsed, list):
                return []

            # Deduplicate by lowercase name
            seen = set()
            wines = []
            for item in parsed:
                if isinstance(item, str):
                    name = item
                    x, y = None, None
                elif isinstance(item, dict):
                    name = item.get('name')
                    x = item.get('x')
                    y = item.get('y')
                else:
                    continue
                if not name:
                    continue
                # Clamp x,y to 0-1 range
                if x is not None and y is not None:
                    try:
                        x = max(0.0, min(1.0, float(x)))
                        y = max(0.0, min(1.0, float(y)))
                    except (ValueError, TypeError):
                        x, y = None, None
                else:
                    x, y = None, None
                key = name.lower().strip()
                if key not in seen:
                    seen.add(key)
                    wines.append({'name': name, 'rating': None, 'x': x, 'y': y})

            logger.info(f"FlashNames: Gemini identified {len(wines)} wines in {elapsed}ms")
            return wines
        except Exception as e:
            logger.error(f"FlashNames: Gemini call failed: {e}", exc_info=True)
            return []

    async def _estimate_ratings(self, unmatched_names: list[str]) -> dict[str, float]:
        """Quick LLM call to estimate ratings for wines not found in DB."""
        if not unmatched_names:
            return {}
        litellm = _get_litellm()
        if not litellm:
            return {}

        t0 = time.perf_counter()
        try:
            prompt = RATING_PROMPT_TEMPLATE.format(wines=json.dumps(unmatched_names))
            response = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.1,
            )
            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            ratings = json.loads(text)
            elapsed = round((time.perf_counter() - t0) * 1000)
            logger.info(f"FlashNames: Estimated ratings for {len(ratings)} wines in {elapsed}ms")
            return {k: round(float(v), 2) for k, v in ratings.items() if v is not None}
        except Exception as e:
            logger.warning(f"FlashNames: Rating estimation failed: {e}")
            return {}

    def _batch_db_lookup(
        self, names: list[str]
    ) -> dict[str, Optional[WineMatch]]:
        """Parallel DB lookups for all wine names.

        Returns: {llm_name: WineMatch or None}
        """
        def lookup(name: str):
            match = self.wine_matcher.match(name)
            if match and match.confidence >= 0.72:
                return (name, match)
            # Try LLM cache
            if self._llm_cache:
                cached = self._llm_cache.get(name)
                if cached:
                    return (name, WineMatch(
                        canonical_name=cached.wine_name,
                        rating=cached.estimated_rating,
                        confidence=cached.confidence,
                        source=WineSource.LLM,
                        wine_type=cached.wine_type,
                        brand=cached.brand,
                        region=cached.region,
                        varietal=cached.varietal,
                        description=getattr(cached, 'blurb', None),
                        wine_id=None,
                    ))
            return (name, None)

        futures = [self._executor.submit(lookup, name) for name in names]
        results = {}
        for future in futures:
            try:
                name, result = future.result()
                results[name] = result
            except Exception as e:
                logger.error(f"FlashNames: DB lookup error: {e}")
        return results

    # Maximum Euclidean distance (in 0-1 space) for spatial matching
    MAX_SPATIAL_DISTANCE = 0.20

    def _merge_with_vision(
        self,
        llm_wines: list[dict],
        llm_ratings: dict[str, Optional[float]],
        db_results: dict,
        vision_result: VisionResult,
        image_bytes: bytes,
    ) -> tuple[list[RecognizedWine], list]:
        """Merge LLM names with Vision bboxes using spatial nearest-neighbor matching.

        If Gemini returned x,y positions, uses Euclidean distance to match each
        LLM wine to the nearest Vision bottle. Falls back to OCR text matching
        if positions are unavailable.
        """
        # Process Vision OCR
        ocr_processor = OCRProcessor()
        ocr_result = ocr_processor.process_with_orphans(
            vision_result.objects, vision_result.text_blocks
        )
        bottle_texts = ocr_result.bottle_texts

        # Check if we have spatial positions from Gemini
        has_positions = any(w.get('x') is not None and w.get('y') is not None for w in llm_wines)

        if has_positions:
            return self._spatial_merge(llm_wines, llm_ratings, db_results, bottle_texts)
        else:
            logger.info("FlashNames: No positions from Gemini, falling back to OCR text matching")
            return self._ocr_text_merge(llm_wines, llm_ratings, db_results, bottle_texts)

    def _spatial_merge(
        self,
        llm_wines: list[dict],
        llm_ratings: dict[str, Optional[float]],
        db_results: dict,
        bottle_texts: list[BottleText],
    ) -> tuple[list[RecognizedWine], list]:
        """Match LLM wines to Vision bottles by spatial nearest-neighbor."""
        recognized: list[RecognizedWine] = []
        fallback = []

        # Compute Vision bottle centers from bboxes
        bottle_centers = [bt.bottle.bbox.center for bt in bottle_texts]

        # Build all (distance, llm_idx, bottle_idx) pairs
        pairs = []
        for li, wine in enumerate(llm_wines):
            lx, ly = wine.get('x'), wine.get('y')
            if lx is None or ly is None:
                continue
            for bi, (bx, by) in enumerate(bottle_centers):
                dist = math.sqrt((lx - bx) ** 2 + (ly - by) ** 2)
                pairs.append((dist, li, bi))

        # Greedy assignment: sort by distance, assign closest first
        pairs.sort()
        used_bottles: set[int] = set()
        used_llm: set[int] = set()

        for dist, li, bi in pairs:
            if li in used_llm or bi in used_bottles:
                continue
            if dist > self.MAX_SPATIAL_DISTANCE:
                break  # All remaining pairs are further away
            used_llm.add(li)
            used_bottles.add(bi)

            wine = llm_wines[li]
            llm_name = wine['name']
            bt = bottle_texts[bi]

            rw = self._build_recognized_wine(llm_name, llm_ratings, db_results, bt, dist)
            recognized.append(rw)
            logger.debug(f"FlashNames: Spatial match '{llm_name}' → bottle {bi} (dist={dist:.3f})")

        # Unmatched LLM wines (no position or beyond threshold) → fallback
        for li, wine in enumerate(llm_wines):
            if li in used_llm:
                continue
            llm_name = wine['name']
            db_match = db_results.get(llm_name)
            canonical = db_match.canonical_name if db_match else None
            rating = db_match.rating if db_match else None
            llm_est_rating = llm_ratings.get(llm_name)
            if rating is None and llm_est_rating is not None:
                rating = llm_est_rating
            wine_name = canonical or llm_name
            if rating is not None:
                fallback.append({'wine_name': wine_name, 'rating': rating})

        # Unmatched Vision bottles → try direct DB fuzzy match on OCR text
        self._match_unmatched_bottles(bottle_texts, used_bottles, recognized)

        return recognized, fallback

    def _ocr_text_merge(
        self,
        llm_wines: list[dict],
        llm_ratings: dict[str, Optional[float]],
        db_results: dict,
        bottle_texts: list[BottleText],
    ) -> tuple[list[RecognizedWine], list]:
        """Fallback: match LLM names to Vision bottles by OCR text similarity."""
        from rapidfuzz import fuzz

        recognized: list[RecognizedWine] = []
        fallback = []
        used_bottles: set[int] = set()

        OCR_MATCH_THRESHOLD = 0.55  # Raised from 0.40

        for wine in llm_wines:
            llm_name = wine['name']
            best_score = 0
            best_bt_idx = -1
            llm_name_lower = llm_name.lower()

            for bt_idx, bt in enumerate(bottle_texts):
                if bt_idx in used_bottles:
                    continue
                ocr_text = (bt.combined_text or "").lower()
                if not ocr_text:
                    continue

                score = fuzz.token_sort_ratio(llm_name_lower, ocr_text) / 100.0
                partial = fuzz.partial_ratio(llm_name_lower, ocr_text) / 100.0
                combined = max(score, partial * 0.9)

                if combined > best_score:
                    best_score = combined
                    best_bt_idx = bt_idx

            if best_score >= OCR_MATCH_THRESHOLD and best_bt_idx >= 0:
                used_bottles.add(best_bt_idx)
                bt = bottle_texts[best_bt_idx]
                rw = self._build_recognized_wine(llm_name, llm_ratings, db_results, bt, best_score)
                recognized.append(rw)
            else:
                db_match = db_results.get(llm_name)
                canonical = db_match.canonical_name if db_match else None
                rating = db_match.rating if db_match else None
                llm_est_rating = llm_ratings.get(llm_name)
                if rating is None and llm_est_rating is not None:
                    rating = llm_est_rating
                wine_name = canonical or llm_name
                if rating is not None:
                    fallback.append({'wine_name': wine_name, 'rating': rating})

        # Unmatched Vision bottles → try direct DB fuzzy match
        self._match_unmatched_bottles(bottle_texts, used_bottles, recognized)

        return recognized, fallback

    def _build_recognized_wine(
        self,
        llm_name: str,
        llm_ratings: dict[str, Optional[float]],
        db_results: dict[str, Optional[WineMatch]],
        bt: BottleText,
        match_quality: float,
    ) -> RecognizedWine:
        """Build a RecognizedWine from an LLM name matched to a Vision bottle."""
        db_match = db_results.get(llm_name)
        canonical = db_match.canonical_name if db_match else None
        rating = db_match.rating if db_match else None
        conf = db_match.confidence if db_match else 0
        llm_est_rating = llm_ratings.get(llm_name)
        if rating is None and llm_est_rating is not None:
            rating = llm_est_rating
        wine_name = canonical or llm_name
        rating_source = RatingSource.DATABASE if canonical else RatingSource.LLM_ESTIMATED
        source = WineSource.DATABASE if canonical else WineSource.LLM

        if canonical:
            confidence = min(0.85, max(0.65, conf if conf > 0 else 0.75))
        else:
            confidence = min(0.75, max(0.65, match_quality if match_quality <= 1.0 else 0.70))

        return RecognizedWine(
            wine_name=wine_name,
            rating=rating,
            confidence=confidence,
            source=source,
            identified=True,
            bottle_text=bt,
            rating_source=rating_source,
            wine_id=db_match.wine_id if db_match else None,
            wine_type=db_match.wine_type if db_match else None,
            brand=db_match.brand if db_match else None,
            region=db_match.region if db_match else None,
            varietal=db_match.varietal if db_match else None,
            blurb=db_match.description if db_match else None,
        )

    def _match_unmatched_bottles(
        self,
        bottle_texts: list[BottleText],
        used_bottles: set[int],
        recognized: list[RecognizedWine],
    ) -> None:
        """Try to match unmatched Vision bottles directly via fuzzy DB match on OCR text."""
        for bt_idx, bt in enumerate(bottle_texts):
            if bt_idx in used_bottles:
                continue
            if bt.normalized_name and len(bt.normalized_name) >= 3:
                match = self.wine_matcher.match(bt.normalized_name)
                if match and match.confidence >= Config.FUZZY_CONFIDENCE_THRESHOLD:
                    existing_names = {r.wine_name.lower() for r in recognized}
                    if match.canonical_name.lower() not in existing_names:
                        recognized.append(RecognizedWine(
                            wine_name=match.canonical_name,
                            rating=match.rating,
                            confidence=min(bt.bottle.confidence, match.confidence),
                            source=WineSource.DATABASE,
                            identified=True,
                            bottle_text=bt,
                            rating_source=RatingSource.DATABASE,
                            wine_id=match.wine_id,
                        ))

    def _names_only_results(
        self,
        llm_wines: list[dict],
        llm_ratings: dict[str, Optional[float]],
        db_results: dict[str, Optional[WineMatch]],
    ) -> tuple[list[RecognizedWine], list]:
        """No Vision data — return all as fallback-style results."""
        fallback = []
        for wine in llm_wines:
            name = wine['name']
            db_match = db_results.get(name)
            canonical = db_match.canonical_name if db_match else None
            rating = db_match.rating if db_match else None
            llm_est_rating = llm_ratings.get(name)
            if rating is None and llm_est_rating is not None:
                rating = llm_est_rating
            wine_name = canonical or name
            if rating is not None:
                fallback.append({'wine_name': wine_name, 'rating': rating})
        return [], fallback

    def _cache_results(self, recognized: list[RecognizedWine], fallback: list) -> None:
        """Cache LLM-discovered wines not in DB."""
        if not self._llm_cache:
            return
        for wine in recognized:
            if wine.source != WineSource.LLM or wine.rating is None:
                continue
            if len(wine.wine_name) > 80:
                continue
            self._llm_cache.set(
                wine_name=wine.wine_name,
                estimated_rating=wine.rating,
                confidence=wine.confidence,
                llm_provider=self.model,
            )
