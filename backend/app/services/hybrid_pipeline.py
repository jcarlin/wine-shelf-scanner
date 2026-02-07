"""
Hybrid parallel pipeline: Vision API + Gemini Flash simultaneously.

Fires Google Vision API (for bounding boxes + OCR) and Gemini Flash (for wine
identification) concurrently via asyncio.gather. Merges results by IoU overlap,
then cross-references against the local DB for authoritative ratings.

Pipeline: [Vision API || Gemini Flash] (max 2-3s) -> Merge + DB validate (0.3s) -> Done

No Claude Vision, no LLM rescue — just two parallel calls and a merge.
"""

import asyncio
import base64
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

from ..config import Config
from ..models.enums import RatingSource, WineSource
from .claude_vision import _compress_image_for_vision
from .fast_pipeline import FAST_PIPELINE_PROMPT, FastPipelineWine, _get_litellm, _parse_llm_response
from .llm_rating_cache import get_llm_rating_cache, LLMRatingCache
from .ocr_processor import BottleText, OCRProcessor
from .recognition_pipeline import RecognizedWine
from .vision import BoundingBox as VisionBBox, DetectedObject, VisionResult, VisionService
from .wine_matcher import WineMatcher, WineMatch

logger = logging.getLogger(__name__)


@dataclass
class HybridPipelineResult:
    """Result from the hybrid pipeline."""
    recognized_wines: list[RecognizedWine]
    fallback: list  # list of FallbackWine-like dicts or objects
    timings: dict = field(default_factory=dict)


def _compute_iou(box1: dict, box2: dict) -> float:
    """Compute Intersection over Union between two bbox dicts {x, y, width, height}."""
    x1 = max(box1['x'], box2['x'])
    y1 = max(box1['y'], box2['y'])
    x2 = min(box1['x'] + box1['width'], box2['x'] + box2['width'])
    y2 = min(box1['y'] + box1['height'], box2['y'] + box2['height'])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)
    area1 = box1['width'] * box1['height']
    area2 = box2['width'] * box2['height']
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def _bbox_to_dict(bbox: VisionBBox) -> dict:
    """Convert a VisionBBox dataclass to a plain dict."""
    return {
        'x': bbox.x,
        'y': bbox.y,
        'width': bbox.width,
        'height': bbox.height,
    }


class HybridPipeline:
    """
    Parallel hybrid pipeline: Vision API + Gemini Flash.

    Flow:
    1. Fire Vision API and Gemini Flash concurrently
    2. Merge by IoU overlap: Vision provides authoritative bboxes,
       Gemini provides wine identifications
    3. Cross-reference against DB for authoritative ratings
    4. Cache LLM-discovered wines
    """

    IOU_MERGE_THRESHOLD = 0.3

    def __init__(
        self,
        wine_matcher: Optional[WineMatcher] = None,
        model: Optional[str] = None,
        use_llm_cache: Optional[bool] = None,
    ):
        self.wine_matcher = wine_matcher or WineMatcher()
        self.model = model or f"gemini/{Config.gemini_model()}"
        self._executor = ThreadPoolExecutor(max_workers=4)

        cache_enabled = use_llm_cache if use_llm_cache is not None else Config.use_llm_cache()
        self._llm_cache: Optional[LLMRatingCache] = get_llm_rating_cache() if cache_enabled else None

    async def scan(self, image_bytes: bytes) -> HybridPipelineResult:
        """Run the hybrid pipeline: Vision + Gemini in parallel, merge, DB lookup."""
        timings: dict[str, float] = {}
        total_start = time.perf_counter()

        # Fire both concurrently
        vision_task = asyncio.get_event_loop().run_in_executor(
            None, self._run_vision, image_bytes
        )
        gemini_task = self._run_gemini(image_bytes)

        vision_result, gemini_wines = await asyncio.gather(
            vision_task, gemini_task, return_exceptions=True
        )

        # Record timing for each leg
        leg_end = time.perf_counter()

        # Handle failures gracefully
        if isinstance(vision_result, Exception):
            logger.warning(f"HybridPipeline: Vision API failed: {vision_result}")
            timings['vision_ms'] = round((leg_end - total_start) * 1000)
            vision_result = None
        if isinstance(gemini_wines, Exception):
            logger.warning(f"HybridPipeline: Gemini failed: {gemini_wines}")
            timings['gemini_ms'] = round((leg_end - total_start) * 1000)
            gemini_wines = []

        # Both failed — nothing we can do
        if vision_result is None and not gemini_wines:
            timings['total_ms'] = round((time.perf_counter() - total_start) * 1000)
            return HybridPipelineResult(
                recognized_wines=[], fallback=[], timings=timings
            )

        # Merge stage
        t_merge = time.perf_counter()
        recognized, fallback = self._merge(vision_result, gemini_wines)
        timings['merge_ms'] = round((time.perf_counter() - t_merge) * 1000)

        # DB lookup stage
        t_db = time.perf_counter()
        recognized = self._validate_against_db(recognized)
        timings['db_lookup_ms'] = round((time.perf_counter() - t_db) * 1000)

        # Cache LLM-only wines
        self._cache_llm_wines(recognized)

        timings['total_ms'] = round((time.perf_counter() - total_start) * 1000)
        logger.info(
            f"HybridPipeline: {len(recognized)} wines recognized, "
            f"{len(fallback)} fallback in {timings['total_ms']}ms "
            f"(merge={timings.get('merge_ms')}ms, db={timings.get('db_lookup_ms')}ms)"
        )

        return HybridPipelineResult(
            recognized_wines=recognized,
            fallback=fallback,
            timings=timings,
        )

    # ------------------------------------------------------------------
    # Internal: run Vision API (synchronous, called via run_in_executor)
    # ------------------------------------------------------------------

    def _run_vision(self, image_bytes: bytes) -> VisionResult:
        """Call Google Vision API (synchronous)."""
        t0 = time.perf_counter()
        service = VisionService()
        result = service.analyze(image_bytes)
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info(
            f"HybridPipeline: Vision API returned {len(result.objects)} objects, "
            f"{len(result.text_blocks)} text blocks in {elapsed}ms"
        )
        return result

    # ------------------------------------------------------------------
    # Internal: run Gemini Flash (async)
    # ------------------------------------------------------------------

    async def _run_gemini(self, image_bytes: bytes) -> list[FastPipelineWine]:
        """Call Gemini Flash Vision (async via litellm)."""
        litellm = _get_litellm()
        if not litellm:
            logger.error("HybridPipeline: litellm not available")
            return []

        compressed = _compress_image_for_vision(image_bytes)
        image_b64 = base64.b64encode(compressed).decode("utf-8")

        t0 = time.perf_counter()
        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}",
                                },
                            },
                            {
                                "type": "text",
                                "text": FAST_PIPELINE_PROMPT,
                            },
                        ],
                    }
                ],
                max_tokens=4000,
                temperature=0.1,
            )
            response_text = response.choices[0].message.content
            wines = _parse_llm_response(response_text)
            elapsed = round((time.perf_counter() - t0) * 1000)
            logger.info(f"HybridPipeline: Gemini identified {len(wines)} wines in {elapsed}ms")
            return wines
        except Exception as e:
            logger.error(f"HybridPipeline: Gemini call failed: {e}", exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Merge: combine Vision bboxes with Gemini identifications
    # ------------------------------------------------------------------

    def _merge(
        self,
        vision_result: Optional[VisionResult],
        gemini_wines: list[FastPipelineWine],
    ) -> tuple[list[RecognizedWine], list]:
        """
        Merge Vision API and Gemini results.

        Strategy:
        1. Both available: IoU-match Gemini names to Vision bottles
        2. Only Vision: OCR text + fuzzy matching
        3. Only Gemini: use Gemini results directly (no Vision bboxes)
        """
        if vision_result is not None and gemini_wines:
            return self._merge_both(vision_result, gemini_wines)
        elif vision_result is not None:
            return self._vision_only(vision_result)
        elif gemini_wines:
            return self._gemini_only(gemini_wines)
        else:
            return [], []

    def _merge_both(
        self,
        vision_result: VisionResult,
        gemini_wines: list[FastPipelineWine],
    ) -> tuple[list[RecognizedWine], list]:
        """Merge when both Vision and Gemini succeeded."""
        recognized: list[RecognizedWine] = []
        fallback = []

        # Process Vision bottles through OCR grouping
        ocr_processor = OCRProcessor()
        ocr_result = ocr_processor.process_with_orphans(
            vision_result.objects, vision_result.text_blocks
        )
        bottle_texts = ocr_result.bottle_texts

        # Track which Gemini wines have been matched
        gemini_matched = [False] * len(gemini_wines)

        for bt in bottle_texts:
            vision_bbox = _bbox_to_dict(bt.bottle.bbox)

            # Find best Gemini match by IoU
            best_iou = 0.0
            best_gemini_idx = -1

            for gi, gw in enumerate(gemini_wines):
                if gemini_matched[gi]:
                    continue
                iou = _compute_iou(vision_bbox, gw.bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_gemini_idx = gi

            if best_iou >= self.IOU_MERGE_THRESHOLD and best_gemini_idx >= 0:
                # Gemini matched this Vision bottle
                gemini_matched[best_gemini_idx] = True
                gw = gemini_wines[best_gemini_idx]

                recognized.append(RecognizedWine(
                    wine_name=gw.wine_name,
                    rating=gw.estimated_rating,
                    confidence=gw.confidence,
                    source=WineSource.LLM,
                    identified=True,
                    bottle_text=bt,
                    rating_source=RatingSource.LLM_ESTIMATED if gw.estimated_rating else RatingSource.NONE,
                    wine_type=gw.wine_type,
                    brand=gw.brand,
                    region=gw.region,
                    varietal=gw.varietal,
                    blurb=gw.blurb,
                ))
            else:
                # No Gemini match for this Vision bottle: fall back to OCR + fuzzy match
                if bt.normalized_name and len(bt.normalized_name) >= 3:
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
                            wine_type=match.wine_type,
                            brand=match.brand,
                            region=match.region,
                            varietal=match.varietal,
                            wine_id=match.wine_id,
                        ))

        # Gemini wines with no Vision bbox → add as fallback
        for gi, gw in enumerate(gemini_wines):
            if not gemini_matched[gi] and gw.wine_name and gw.estimated_rating is not None:
                fallback.append({
                    'wine_name': gw.wine_name,
                    'rating': gw.estimated_rating,
                })

        return recognized, fallback

    def _vision_only(
        self,
        vision_result: VisionResult,
    ) -> tuple[list[RecognizedWine], list]:
        """Vision API only — process through OCR + fuzzy matching."""
        recognized: list[RecognizedWine] = []

        ocr_processor = OCRProcessor()
        ocr_result = ocr_processor.process_with_orphans(
            vision_result.objects, vision_result.text_blocks
        )

        for bt in ocr_result.bottle_texts:
            if bt.normalized_name and len(bt.normalized_name) >= 3:
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
                        wine_type=match.wine_type,
                        brand=match.brand,
                        region=match.region,
                        varietal=match.varietal,
                        wine_id=match.wine_id,
                    ))

        return recognized, []

    def _gemini_only(
        self,
        gemini_wines: list[FastPipelineWine],
    ) -> tuple[list[RecognizedWine], list]:
        """Gemini only (Vision failed) — use Gemini bboxes and names."""
        recognized: list[RecognizedWine] = []

        for gw in gemini_wines:
            if not gw.wine_name:
                continue

            # Create synthetic BottleText from Gemini bbox
            bt = BottleText(
                bottle=DetectedObject(
                    name="Bottle",
                    confidence=gw.confidence,
                    bbox=VisionBBox(
                        x=gw.bbox.get("x", 0),
                        y=gw.bbox.get("y", 0),
                        width=gw.bbox.get("width", 0),
                        height=gw.bbox.get("height", 0),
                    ),
                ),
                text_fragments=[gw.wine_name],
                combined_text=gw.wine_name,
                normalized_name=gw.wine_name,
            )

            recognized.append(RecognizedWine(
                wine_name=gw.wine_name,
                rating=gw.estimated_rating,
                confidence=gw.confidence,
                source=WineSource.LLM,
                identified=True,
                bottle_text=bt,
                rating_source=RatingSource.LLM_ESTIMATED if gw.estimated_rating else RatingSource.NONE,
                wine_type=gw.wine_type,
                brand=gw.brand,
                region=gw.region,
                varietal=gw.varietal,
                blurb=gw.blurb,
            ))

        return recognized, []

    # ------------------------------------------------------------------
    # DB validation: cross-reference recognized wines against database
    # ------------------------------------------------------------------

    def _validate_against_db(
        self,
        wines: list[RecognizedWine],
    ) -> list[RecognizedWine]:
        """Cross-reference wines against the DB for authoritative ratings."""
        def lookup(wine: RecognizedWine) -> RecognizedWine:
            # Already from DB — skip
            if wine.source == WineSource.DATABASE:
                return wine

            db_match = self.wine_matcher.match(wine.wine_name)
            if db_match and db_match.confidence >= 0.80:
                return RecognizedWine(
                    wine_name=db_match.canonical_name,
                    rating=db_match.rating,
                    confidence=min(wine.confidence, db_match.confidence),
                    source=WineSource.DATABASE,
                    identified=True,
                    bottle_text=wine.bottle_text,
                    rating_source=RatingSource.DATABASE,
                    wine_type=db_match.wine_type or wine.wine_type,
                    brand=db_match.brand or wine.brand,
                    region=db_match.region or wine.region,
                    varietal=db_match.varietal or wine.varietal,
                    blurb=wine.blurb,
                    wine_id=db_match.wine_id,
                )
            else:
                # Cap confidence for LLM-only wines
                if wine.rating is not None:
                    capped = min(wine.confidence, 0.75)
                    rating_source = wine.rating_source
                else:
                    capped = min(wine.confidence, 0.65)
                    rating_source = RatingSource.NONE

                return RecognizedWine(
                    wine_name=wine.wine_name,
                    rating=wine.rating,
                    confidence=capped,
                    source=WineSource.LLM,
                    identified=True,
                    bottle_text=wine.bottle_text,
                    rating_source=rating_source,
                    wine_type=wine.wine_type,
                    brand=wine.brand,
                    region=wine.region,
                    varietal=wine.varietal,
                    blurb=wine.blurb,
                )

        futures = [self._executor.submit(lookup, w) for w in wines]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except Exception as e:
                logger.error(f"HybridPipeline: DB lookup failed: {e}", exc_info=True)

        return results

    # ------------------------------------------------------------------
    # Cache LLM-discovered wines
    # ------------------------------------------------------------------

    def _cache_llm_wines(self, recognized_wines: list[RecognizedWine]) -> None:
        """Cache LLM-identified wines not in DB for future lookups."""
        if not self._llm_cache:
            return

        for wine in recognized_wines:
            if wine.source != WineSource.LLM:
                continue
            if wine.rating is None:
                continue
            if len(wine.wine_name) > 80 or len(wine.wine_name.split()) > 10:
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
                blurb=wine.blurb,
            )
