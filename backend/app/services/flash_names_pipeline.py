"""
Flash Names pipeline: single-prompt LLM + parallel Vision API.

Strategy:
1. Fire Gemini Flash (names + positions + ratings + metadata) and Vision API concurrently
2. LLM returns wine names, estimated ratings, and full metadata (~2-3s)
3. Vision API returns bboxes + OCR (~2-3s)
4. Merge: assign LLM names to Vision bboxes via spatial matching or OCR similarity
5. Parallel DB lookups for authoritative data (DB overrides LLM estimates)

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


FAST_SCAN_PROMPT = """Carefully examine this photo of a wine shelf. Count EVERY wine bottle visible, including partially obscured ones and bottles in back rows.

For each bottle return: name (producer + wine + vintage if visible), bounding box as x, y (top-left corner), w, h (width, height) — all as fractions 0.0-1.0 of image dimensions — and estimated Vivino community rating (1.0-5.0).

Be thorough: a typical shelf photo contains 8-20 bottles. Do NOT stop early. List every bottle you can identify, even if the label is only partially readable.

Return ONLY a JSON array:
[{"name": "Caymus Cabernet Sauvignon Napa Valley 2021", "x": 0.10, "y": 0.30, "w": 0.08, "h": 0.25, "rating": 4.4}]"""

FULL_METADATA_PROMPT = """Carefully examine this photo of a wine shelf. Count EVERY wine bottle visible, including partially obscured ones and bottles in back rows.

For each bottle, return a JSON object with:
- name: full wine name (producer + wine + vintage if visible)
- x, y: top-left corner of the bottle as fractions (0.0-1.0, top-left origin)
- w, h: width and height of the bottle as fractions (0.0-1.0)
- rating: estimated Vivino community rating (1.0-5.0). Most wines 3.5-4.3, premium 4.3-4.7, iconic 4.7+
- type: wine type (Red, White, Rosé, Sparkling, Dessert)
- varietal: grape variety (e.g. Cabernet Sauvignon, Pinot Noir, Chardonnay)
- region: wine region (e.g. Napa Valley, Burgundy, Barossa Valley)
- brand: winery/producer name

Be thorough: a typical shelf photo contains 8-20 bottles. Do NOT stop early. List every bottle you can identify.

Return ONLY a JSON array:
[{"name": "Caymus Cabernet Sauvignon Napa Valley", "x": 0.10, "y": 0.30, "w": 0.08, "h": 0.25, "rating": 4.4, "type": "Red", "varietal": "Cabernet Sauvignon", "region": "Napa Valley", "brand": "Caymus Vineyards"}]

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
    Single-prompt LLM pipeline with parallel Vision API for bboxes.

    Flow:
    1. [Parallel] Gemini Flash (names + ratings + metadata) + Vision API
    2. OCR grouping from Vision results
    3. Spatial or OCR-text merge of LLM names to Vision bottles
    4. DB lookups for authoritative data (overrides LLM estimates)
    5. Unmatched LLM names -> fallback list with LLM-estimated ratings
    """

    def __init__(
        self,
        wine_matcher: Optional[WineMatcher] = None,
        model: Optional[str] = None,
        use_llm_cache: Optional[bool] = None,
    ):
        self.wine_matcher = wine_matcher or WineMatcher()
        override = Config.flash_names_model()
        self.model = model or (override if override else f"gemini/{Config.fast_pipeline_model()}")
        self._executor = ThreadPoolExecutor(max_workers=8)
        cache_enabled = use_llm_cache if use_llm_cache is not None else Config.use_llm_cache()
        self._llm_cache: Optional[LLMRatingCache] = get_llm_rating_cache() if cache_enabled else None

    async def scan_progressive(self, image_bytes: bytes):
        """Yield turbo results first, then Gemini-enhanced results.

        Async generator that yields FlashNamesResult twice:
        - Phase 1: Vision API + OCR grouping + DB fuzzy matching (turbo-quality, ~3.5s)
        - Phase 2: Gemini merge + full metadata (enhanced, ~6-8s)

        Both phases yield complete FlashNamesResult objects. Phase 2 is a full
        replacement — the consumer should swap its entire state.
        """
        total_start = time.perf_counter()

        # Fire both concurrently
        gemini_task = asyncio.create_task(self._run_gemini_names(image_bytes))
        vision_coro = asyncio.get_event_loop().run_in_executor(
            None, self._run_vision, image_bytes
        )

        # Wait for Vision first (typically faster at ~2.5s vs Gemini ~6-8s)
        try:
            vision_result = await vision_coro
        except Exception as e:
            logger.warning(f"FlashNames progressive: Vision API failed: {e}")
            vision_result = None

        # Phase 1: Process Vision results immediately (turbo-style)
        phase1_recognized = []
        if vision_result and vision_result.objects:
            phase1_recognized = self._turbo_match_vision(vision_result, image_bytes)

        if phase1_recognized:
            phase1_ms = round((time.perf_counter() - total_start) * 1000)
            logger.info(
                f"FlashNames progressive phase1: {len(phase1_recognized)} results in {phase1_ms}ms"
            )
            yield FlashNamesResult(
                recognized_wines=phase1_recognized,
                fallback=[],
                timings={
                    'phase': 1,
                    'total_ms': phase1_ms,
                    'vision_bottles': len(vision_result.objects) if vision_result else 0,
                    'llm_wines': 0,
                    'ocr_texts_count': 0,
                },
            )

        # Phase 2: Wait for Gemini, merge everything
        try:
            llm_wines = await gemini_task
        except Exception as e:
            logger.warning(f"FlashNames progressive: Gemini failed: {e}")
            llm_wines = []

        if not llm_wines:
            # Gemini failed — re-yield phase1 as final result if we have it
            vision_bottles = len(vision_result.objects) if vision_result else 0
            if phase1_recognized:
                phase2_ms = round((time.perf_counter() - total_start) * 1000)
                yield FlashNamesResult(
                    recognized_wines=phase1_recognized,
                    fallback=[],
                    timings={
                        'phase': 2, 'total_ms': phase2_ms,
                        'vision_bottles': vision_bottles, 'llm_wines': 0, 'ocr_texts_count': 0,
                    },
                )
            else:
                yield FlashNamesResult(
                    recognized_wines=[], fallback=[],
                    timings={
                        'phase': 2, 'total_ms': round((time.perf_counter() - total_start) * 1000),
                        'vision_bottles': vision_bottles, 'llm_wines': 0, 'ocr_texts_count': 0,
                    },
                )
            return

        # Full merge logic (same as scan())
        llm_names = [w['name'] for w in llm_wines]
        llm_ratings = {w['name']: w.get('rating') for w in llm_wines}
        llm_metadata = {w['name']: w for w in llm_wines}

        db_results = self._batch_db_lookup(llm_names)

        for name in llm_names:
            db_match = db_results.get(name)
            db_rating = db_match.rating if db_match else None
            if db_rating is None and llm_ratings.get(name) is None:
                llm_ratings[name] = 3.5

        if vision_result and vision_result.objects:
            recognized, fallback = self._merge_with_vision(
                llm_wines, llm_ratings, db_results, vision_result, image_bytes,
                llm_metadata=llm_metadata,
            )
        else:
            recognized, fallback = self._names_only_results(llm_wines, llm_ratings, db_results)

        # Carry forward phase 1 DB ratings that phase 2 may have lost
        if phase1_recognized:
            recognized = self._carry_forward_phase1_ratings(phase1_recognized, recognized)

        self._cache_results(recognized, fallback)

        phase2_ms = round((time.perf_counter() - total_start) * 1000)
        logger.info(
            f"FlashNames progressive phase2: {len(recognized)} results, "
            f"{len(fallback)} fallback in {phase2_ms}ms"
        )

        yield FlashNamesResult(
            recognized_wines=recognized,
            fallback=fallback,
            timings={
                'phase': 2,
                'total_ms': phase2_ms,
                'vision_bottles': len(vision_result.objects) if vision_result else 0,
                'llm_wines': len(llm_wines),
                'ocr_texts_count': sum(1 for rw in recognized if rw.bottle_text is not None),
            },
        )

    def _turbo_match_vision(
        self,
        vision_result: VisionResult,
        image_bytes: bytes,
    ) -> list[RecognizedWine]:
        """Process Vision results with OCR grouping + parallel DB fuzzy matching.

        This is the turbo-quality path: no LLM, just Vision API + DB.
        Returns recognized wines with bboxes for immediate display.
        """
        ocr_processor = OCRProcessor()
        ocr_result = ocr_processor.process_with_orphans(
            vision_result.objects, vision_result.text_blocks
        )
        bottle_texts = ocr_result.bottle_texts

        recognized: list[RecognizedWine] = []
        for bt in bottle_texts:
            if not bt.normalized_name or len(bt.normalized_name) < 3:
                continue
            match = self.wine_matcher.match(bt.normalized_name)
            if match and match.confidence >= Config.FUZZY_CONFIDENCE_THRESHOLD:
                recognized.append(RecognizedWine(
                    wine_name=match.canonical_name,
                    rating=match.rating,
                    confidence=min(bt.bottle.confidence, match.confidence),
                    source=WineSource.DATABASE,
                    identified=True,
                    bottle_text=bt,
                    rating_source=RatingSource.DATABASE,
                    wine_id=match.wine_id,
                    wine_type=match.wine_type,
                    brand=match.brand,
                    region=match.region,
                    varietal=match.varietal,
                    blurb=match.description,
                ))

            # Also check LLM cache for non-DB matches
            elif self._llm_cache:
                cached = self._llm_cache.get(bt.normalized_name)
                if cached:
                    recognized.append(RecognizedWine(
                        wine_name=cached.wine_name,
                        rating=cached.estimated_rating,
                        confidence=min(bt.bottle.confidence, cached.confidence),
                        source=WineSource.LLM,
                        identified=True,
                        bottle_text=bt,
                        rating_source=RatingSource.LLM_ESTIMATED,
                        wine_type=cached.wine_type,
                        brand=cached.brand,
                        region=cached.region,
                        varietal=cached.varietal,
                    ))

        return recognized

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
            timings['vision_bottles'] = len(vision_result.objects) if vision_result else 0
            timings['llm_wines'] = 0
            timings['ocr_texts_count'] = 0
            return FlashNamesResult(recognized_wines=[], fallback=[], timings=timings)

        # Extract names, ratings, and metadata for DB lookup
        llm_names = [w['name'] for w in llm_wines]
        llm_ratings = {w['name']: w.get('rating') for w in llm_wines}
        llm_metadata = {w['name']: w for w in llm_wines}

        # DB lookups (parallel)
        t_db = time.perf_counter()
        db_results = self._batch_db_lookup(llm_names)
        timings['db_ms'] = round((time.perf_counter() - t_db) * 1000)

        # Last-resort default for any unrated wines not in DB
        for name in llm_names:
            db_match = db_results.get(name)
            db_rating = db_match.rating if db_match else None
            if db_rating is None and llm_ratings.get(name) is None:
                llm_ratings[name] = 3.5

        # Merge with Vision bboxes if available
        t_merge = time.perf_counter()
        if vision_result and vision_result.objects:
            recognized, fallback = self._merge_with_vision(
                llm_wines, llm_ratings, db_results, vision_result, image_bytes,
                llm_metadata=llm_metadata,
            )
        else:
            recognized, fallback = self._names_only_results(llm_wines, llm_ratings, db_results)
        timings['merge_ms'] = round((time.perf_counter() - t_merge) * 1000)

        # Cache LLM-discovered wines
        self._cache_results(recognized, fallback)

        timings['vision_bottles'] = len(vision_result.objects) if vision_result else 0
        timings['llm_wines'] = len(llm_wines)
        timings['ocr_texts_count'] = sum(1 for rw in recognized if rw.bottle_text is not None)
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
    def _compress_for_llm(image_bytes: bytes, max_dim: int = 0, quality: int = 0) -> bytes:
        """Compress image for LLM call — smaller than Vision API needs."""
        from PIL import Image as PILImage
        if max_dim <= 0:
            max_dim = Config.llm_image_max_dim()
        if quality <= 0:
            quality = Config.llm_image_quality()
        img = PILImage.open(io.BytesIO(image_bytes))
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim))
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality)
        return buf.getvalue()

    async def _run_gemini_names(self, image_bytes: bytes) -> list[dict]:
        """Call Gemini Flash with names+metadata prompt. Returns list of wine dicts with name, rating, position, and metadata."""
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
                        {"type": "text", "text": FAST_SCAN_PROMPT},
                    ],
                }],
                max_tokens=Config.flash_names_max_tokens(),
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
                    x, y, w, h = None, None, None, None
                elif isinstance(item, dict):
                    name = item.get('name')
                    x = item.get('x')
                    y = item.get('y')
                    w = item.get('w')
                    h = item.get('h')
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
                # Parse w,h with reasonable clamping
                if w is not None and h is not None:
                    try:
                        w = max(0.02, min(0.5, float(w)))
                        h = max(0.05, min(0.8, float(h)))
                    except (ValueError, TypeError):
                        w, h = None, None
                else:
                    w, h = None, None
                # Parse rating
                rating = item.get('rating') if isinstance(item, dict) else None
                if rating is not None:
                    try:
                        rating = round(max(1.0, min(5.0, float(rating))), 2)
                    except (ValueError, TypeError):
                        rating = None

                # Parse metadata fields
                if isinstance(item, dict):
                    wine_type = item.get('type')
                    varietal = item.get('varietal')
                    region = item.get('region')
                    brand = item.get('brand')
                else:
                    wine_type = varietal = region = brand = None

                key = name.lower().strip()
                if key not in seen:
                    seen.add(key)
                    wines.append({
                        'name': name, 'rating': rating, 'x': x, 'y': y,
                        'w': w, 'h': h,
                        'wine_type': wine_type, 'varietal': varietal,
                        'region': region, 'brand': brand,
                    })

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
    MAX_SPATIAL_DISTANCE = 0.25

    def _merge_with_vision(
        self,
        llm_wines: list[dict],
        llm_ratings: dict[str, Optional[float]],
        db_results: dict,
        vision_result: VisionResult,
        image_bytes: bytes,
        llm_metadata: Optional[dict] = None,
    ) -> tuple[list[RecognizedWine], list]:
        """Merge LLM names with Vision bboxes using spatial nearest-neighbor matching.

        If Gemini returned x,y positions, uses Euclidean distance to match each
        LLM wine to the nearest Vision bottle. Falls back to OCR text matching
        if positions are unavailable.
        """
        if llm_metadata is None:
            llm_metadata = {}

        # Process Vision OCR
        ocr_processor = OCRProcessor()
        ocr_result = ocr_processor.process_with_orphans(
            vision_result.objects, vision_result.text_blocks
        )
        bottle_texts = ocr_result.bottle_texts

        # Check if we have spatial positions from Gemini
        has_positions = any(w.get('x') is not None and w.get('y') is not None for w in llm_wines)

        if has_positions:
            return self._spatial_merge(llm_wines, llm_ratings, db_results, bottle_texts, llm_metadata)
        else:
            logger.info("FlashNames: No positions from Gemini, falling back to OCR text matching")
            return self._ocr_text_merge(llm_wines, llm_ratings, db_results, bottle_texts, llm_metadata)

    def _spatial_merge(
        self,
        llm_wines: list[dict],
        llm_ratings: dict[str, Optional[float]],
        db_results: dict,
        bottle_texts: list[BottleText],
        llm_metadata: Optional[dict] = None,
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
            # Compute center from top-left + dimensions if available
            lw, lh = wine.get('w'), wine.get('h')
            if lw is not None and lh is not None:
                cx = lx + lw / 2
                cy = ly + lh / 2
            else:
                cx, cy = lx, ly
            for bi, (bx, by) in enumerate(bottle_centers):
                dist = math.sqrt((cx - bx) ** 2 + (cy - by) ** 2)
                pairs.append((dist, li, bi))

        # Greedy assignment: sort by distance, assign closest first
        pairs.sort()
        used_bottles: set[int] = set()
        used_llm: set[int] = set()
        matched_pairs: list[tuple[int, int]] = []  # (llm_idx, bottle_idx)

        for dist, li, bi in pairs:
            if li in used_llm or bi in used_bottles:
                continue
            if dist > self.MAX_SPATIAL_DISTANCE:
                break  # All remaining pairs are further away
            used_llm.add(li)
            used_bottles.add(bi)
            matched_pairs.append((li, bi))

            wine = llm_wines[li]
            llm_name = wine['name']
            bt = bottle_texts[bi]

            rw = self._build_recognized_wine(llm_name, llm_ratings, db_results, bt, dist, llm_metadata or {})
            recognized.append(rw)
            logger.debug(f"FlashNames: Spatial match '{llm_name}' → bottle {bi} (dist={dist:.3f})")

        # Second-chance: try OCR text matching for spatially unmatched LLM wines
        spatial_matched = len(used_llm)
        from rapidfuzz import fuzz
        OCR_MATCH_THRESHOLD = 0.55
        for li, wine in enumerate(llm_wines):
            if li in used_llm:
                continue
            llm_name = wine['name']
            llm_name_lower = llm_name.lower()
            best_score = 0
            best_bt_idx = -1
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
                used_llm.add(li)
                used_bottles.add(best_bt_idx)
                matched_pairs.append((li, best_bt_idx))
                bt = bottle_texts[best_bt_idx]
                rw = self._build_recognized_wine(llm_name, llm_ratings, db_results, bt, best_score, llm_metadata or {})
                recognized.append(rw)
                logger.debug(f"FlashNames: OCR fallback match '{llm_name}' → bottle {best_bt_idx} (score={best_score:.3f})")

        ocr_matched = len(used_llm) - spatial_matched
        logger.info(
            f"FlashNames: Spatial merge: {spatial_matched}/{len(llm_wines)} spatial, "
            f"{ocr_matched} OCR fallback, "
            f"{len(used_bottles)}/{len(bottle_texts)} Vision matched"
        )

        # Compute per-image calibration offset from matched pairs.
        # Gemini positions can be systematically offset from Vision bottle
        # centers; this corrects synthetic bboxes using the known error.
        MAX_CALIBRATION = 0.08
        offsets_x: list[float] = []
        offsets_y: list[float] = []
        for li, bi in matched_pairs:
            wine = llm_wines[li]
            lx, ly = wine.get('x'), wine.get('y')
            if lx is not None and ly is not None:
                lw, lh = wine.get('w'), wine.get('h')
                if lw is not None and lh is not None:
                    cx = lx + lw / 2
                    cy = ly + lh / 2
                else:
                    cx, cy = lx, ly
                bx, by = bottle_centers[bi]
                offsets_x.append(bx - cx)
                offsets_y.append(by - cy)

        cal_x = sum(offsets_x) / len(offsets_x) if offsets_x else 0.0
        cal_y = sum(offsets_y) / len(offsets_y) if offsets_y else 0.0
        # Reject extreme corrections (> 8% of image) as noise
        if abs(cal_x) > MAX_CALIBRATION:
            cal_x = 0.0
        if abs(cal_y) > MAX_CALIBRATION:
            cal_y = 0.0
        if cal_x != 0 or cal_y != 0:
            logger.info(
                f"FlashNames: Position calibration dx={cal_x:.3f}, dy={cal_y:.3f} "
                f"from {len(offsets_x)} pairs"
            )

        # Unmatched LLM wines: create synthetic bboxes from Gemini positions
        # (with calibration), or fall back to list if no position available.
        DEFAULT_BOTTLE_WIDTH = 0.08
        DEFAULT_BOTTLE_HEIGHT = 0.25
        synthetic_count = 0

        for li, wine in enumerate(llm_wines):
            if li in used_llm:
                continue
            llm_name = wine['name']
            lx, ly = wine.get('x'), wine.get('y')

            if lx is not None and ly is not None:
                # Use Gemini-provided dimensions if available, else defaults
                lw = wine.get('w')
                lh = wine.get('h')
                has_gemini_bbox = lw is not None and lh is not None
                bbox_w = lw if has_gemini_bbox else DEFAULT_BOTTLE_WIDTH
                bbox_h = lh if has_gemini_bbox else DEFAULT_BOTTLE_HEIGHT

                # Compute center from top-left + dimensions, then apply calibration
                if has_gemini_bbox:
                    center_x = lx + lw / 2 + cal_x
                    center_y = ly + lh / 2 + cal_y
                else:
                    center_x = lx + cal_x
                    center_y = ly + cal_y

                synthetic_bbox = VisionBBox(
                    x=max(0.0, center_x - bbox_w / 2),
                    y=max(0.0, center_y - bbox_h / 2),
                    width=bbox_w,
                    height=bbox_h,
                )
                synthetic_obj = DetectedObject(name="Bottle", confidence=0.70, bbox=synthetic_bbox)
                synthetic_bt = BottleText(
                    bottle=synthetic_obj,
                    text_fragments=[],
                    combined_text="",
                    normalized_name="",
                )
                rw = self._build_recognized_wine(
                    llm_name, llm_ratings, db_results, synthetic_bt, 0.0, llm_metadata or {}
                )
                # Higher confidence cap when Gemini provides bbox dimensions
                conf_cap = 0.80 if has_gemini_bbox else 0.70
                rw.confidence = min(rw.confidence, conf_cap)
                recognized.append(rw)
                synthetic_count += 1
                logger.debug(
                    f"FlashNames: Synthetic bbox for '{llm_name}' at "
                    f"({center_x:.2f}, {center_y:.2f}) size=({bbox_w:.2f}x{bbox_h:.2f}) "
                    f"[raw: ({lx:.2f}, {ly:.2f})] gemini_bbox={has_gemini_bbox}"
                )
            else:
                # No position at all → fallback (can't place overlay)
                db_match = db_results.get(llm_name)
                canonical = db_match.canonical_name if db_match else None
                rating = db_match.rating if db_match else None
                llm_est_rating = llm_ratings.get(llm_name)
                if rating is None and llm_est_rating is not None:
                    rating = llm_est_rating
                wine_name = canonical or llm_name
                if rating is not None:
                    fallback.append({'wine_name': wine_name, 'rating': rating})

        logger.info(
            f"FlashNames: Final: {len(recognized)} recognized ({synthetic_count} synthetic), "
            f"{len(fallback)} fallback"
        )

        # Unmatched Vision bottles → try direct DB fuzzy match on OCR text
        self._match_unmatched_bottles(bottle_texts, used_bottles, recognized)

        return recognized, fallback

    def _ocr_text_merge(
        self,
        llm_wines: list[dict],
        llm_ratings: dict[str, Optional[float]],
        db_results: dict,
        bottle_texts: list[BottleText],
        llm_metadata: Optional[dict] = None,
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
                rw = self._build_recognized_wine(llm_name, llm_ratings, db_results, bt, best_score, llm_metadata or {})
                recognized.append(rw)
            else:
                # Try synthetic bbox from Gemini position
                DEFAULT_BOTTLE_WIDTH = 0.08
                DEFAULT_BOTTLE_HEIGHT = 0.25
                lx, ly = wine.get('x'), wine.get('y')

                if lx is not None and ly is not None:
                    lw = wine.get('w')
                    lh = wine.get('h')
                    has_gemini_bbox = lw is not None and lh is not None
                    bbox_w = lw if has_gemini_bbox else DEFAULT_BOTTLE_WIDTH
                    bbox_h = lh if has_gemini_bbox else DEFAULT_BOTTLE_HEIGHT

                    if has_gemini_bbox:
                        center_x = lx + lw / 2
                        center_y = ly + lh / 2
                    else:
                        center_x, center_y = lx, ly

                    synthetic_bbox = VisionBBox(
                        x=max(0.0, center_x - bbox_w / 2),
                        y=max(0.0, center_y - bbox_h / 2),
                        width=bbox_w,
                        height=bbox_h,
                    )
                    synthetic_obj = DetectedObject(name="Bottle", confidence=0.70, bbox=synthetic_bbox)
                    synthetic_bt = BottleText(
                        bottle=synthetic_obj,
                        text_fragments=[],
                        combined_text="",
                        normalized_name="",
                    )
                    rw = self._build_recognized_wine(
                        llm_name, llm_ratings, db_results, synthetic_bt, 0.0, llm_metadata or {}
                    )
                    conf_cap = 0.80 if has_gemini_bbox else 0.70
                    rw.confidence = min(rw.confidence, conf_cap)
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
        llm_metadata: Optional[dict] = None,
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

        # For non-DB wines, use LLM metadata
        meta = (llm_metadata or {}).get(llm_name, {})

        return RecognizedWine(
            wine_name=wine_name,
            rating=rating,
            confidence=confidence,
            source=source,
            identified=True,
            bottle_text=bt,
            rating_source=rating_source,
            wine_id=db_match.wine_id if db_match else None,
            wine_type=db_match.wine_type if db_match else meta.get('wine_type'),
            brand=db_match.brand if db_match else meta.get('brand'),
            region=db_match.region if db_match else meta.get('region'),
            varietal=db_match.varietal if db_match else meta.get('varietal'),
            blurb=db_match.description if db_match else None,
            review_snippets=None,
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

    @staticmethod
    def _carry_forward_phase1_ratings(
        phase1_recognized: list[RecognizedWine],
        phase2_recognized: list[RecognizedWine],
    ) -> list[RecognizedWine]:
        """Preserve phase 1 DB ratings that phase 2 may have lost.

        Phase 1 finds DB ratings via OCR text fuzzy matching. Phase 2 re-does
        DB lookups using Gemini's name strings, which may not match the same DB
        entries. This causes ratings to jump (e.g. 4.5 → 4.2) between SSE phases.

        Fix: for each phase 2 wine with an LLM-estimated rating, check if the
        same bottle (by bbox) had a DB rating in phase 1. If so, carry forward
        the DB rating and identity while keeping phase 2's richer metadata.
        Also re-merge any phase 1 DB-matched wines that phase 2 dropped entirely.
        """
        # Build lookup: bbox tuple → phase 1 wine (DB-matched only)
        p1_by_bbox: dict[tuple[float, float, float, float], RecognizedWine] = {}
        for rw in phase1_recognized:
            if rw.rating_source != RatingSource.DATABASE:
                continue
            if rw.bottle_text and rw.bottle_text.bottle and rw.bottle_text.bottle.bbox:
                bbox = rw.bottle_text.bottle.bbox
                key = (bbox.x, bbox.y, bbox.width, bbox.height)
                p1_by_bbox[key] = rw

        if not p1_by_bbox:
            return phase2_recognized

        # Track which phase 1 bboxes are covered by phase 2
        covered_bboxes: set[tuple[float, float, float, float]] = set()
        carried = 0

        for rw in phase2_recognized:
            if not rw.bottle_text or not rw.bottle_text.bottle or not rw.bottle_text.bottle.bbox:
                continue
            bbox = rw.bottle_text.bottle.bbox
            key = (bbox.x, bbox.y, bbox.width, bbox.height)
            covered_bboxes.add(key)

            # Only override LLM-estimated ratings with phase 1 DB ratings
            if rw.rating_source != RatingSource.LLM_ESTIMATED:
                continue

            p1_wine = p1_by_bbox.get(key)
            if not p1_wine:
                continue

            # Carry forward DB identity from phase 1
            rw.rating = p1_wine.rating
            rw.rating_source = p1_wine.rating_source
            rw.wine_name = p1_wine.wine_name
            rw.wine_id = p1_wine.wine_id
            rw.source = p1_wine.source

            # Keep phase 2 metadata if present, backfill from phase 1 if missing
            if not rw.wine_type and p1_wine.wine_type:
                rw.wine_type = p1_wine.wine_type
            if not rw.varietal and p1_wine.varietal:
                rw.varietal = p1_wine.varietal
            if not rw.region and p1_wine.region:
                rw.region = p1_wine.region
            if not rw.brand and p1_wine.brand:
                rw.brand = p1_wine.brand
            if not rw.blurb and p1_wine.blurb:
                rw.blurb = p1_wine.blurb

            carried += 1

        # Re-merge phase 1 DB wines that phase 2 dropped entirely
        remerged = 0
        phase2_names = {rw.wine_name.lower() for rw in phase2_recognized}
        for bbox_key, p1_wine in p1_by_bbox.items():
            if bbox_key in covered_bboxes:
                continue
            if p1_wine.wine_name.lower() in phase2_names:
                continue
            phase2_recognized.append(p1_wine)
            remerged += 1

        if carried or remerged:
            logger.info(
                f"FlashNames: Carried forward {carried} DB ratings from phase1, "
                f"re-merged {remerged} dropped wines"
            )

        return phase2_recognized

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
                wine_type=wine.wine_type,
                region=wine.region,
                varietal=wine.varietal,
                brand=wine.brand,
            )
