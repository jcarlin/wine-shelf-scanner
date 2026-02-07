"""
Turbo wine recognition pipeline.

Keeps Vision API for accurate OCR/bounding boxes but skips the two slowest
stages (Claude Vision fallback and LLM rescue). Unmatched bottles go straight
to the fallback list.

Pipeline: Vision API (2-3s) -> OCR grouping (10ms) -> Fuzzy Match + Single LLM Batch (0.5-1.5s) -> Done

Expected latency: 3-5s total vs 8-14s for the legacy pipeline.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from ..config import Config
from ..models.enums import RatingSource, WineSource
from .ocr_processor import BottleText, OCRProcessor, OCRProcessingResult, OrphanedText
from .recognition_pipeline import RecognizedWine, RecognitionPipeline
from .vision import VisionResult, VisionService
from .wine_matcher import WineMatcher

logger = logging.getLogger(__name__)


@dataclass
class TurboPipelineResult:
    """Result from the turbo pipeline."""
    recognized_wines: list[RecognizedWine]
    fallback: list  # list of FallbackWine
    orphaned_texts: list[OrphanedText]
    timings: dict = field(default_factory=dict)
    debug_data: Optional[dict] = None


class TurboPipeline:
    """
    Turbo pipeline: Vision API + OCR + Fuzzy/LLM match, no Vision fallback or rescue.

    Flow:
    1. Google Vision API for object detection + OCR
    2. OCR grouping (text -> bottle assignment)
    3. Fuzzy match + single LLM batch validation
    4. Unmatched bottles -> fallback list
    """

    def __init__(
        self,
        image_bytes: bytes,
        wine_matcher: WineMatcher,
        use_llm: bool = True,
        debug_mode: bool = False,
    ):
        self.image_bytes = image_bytes
        self.wine_matcher = wine_matcher
        self.use_llm = use_llm
        self.debug_mode = debug_mode

    async def run(self) -> TurboPipelineResult:
        """
        Run the turbo pipeline.

        Returns:
            TurboPipelineResult with recognized wines, fallback, and timing data.
        """
        timings: dict = {}
        total_start = time.perf_counter()

        # Stage 1: Vision API
        t0 = time.perf_counter()
        vision_service = VisionService()
        vision_result = vision_service.analyze(self.image_bytes)
        timings["vision_ms"] = round((time.perf_counter() - t0) * 1000)
        logger.info(
            f"TurboPipeline: Vision API detected {len(vision_result.objects)} bottles "
            f"in {timings['vision_ms']}ms"
        )

        if not vision_result.objects:
            timings["total_ms"] = round((time.perf_counter() - total_start) * 1000)
            return TurboPipelineResult(
                recognized_wines=[],
                fallback=[],
                orphaned_texts=[],
                timings=timings,
                debug_data={"vision_result": vision_result} if self.debug_mode else None,
            )

        # Stage 2: OCR grouping
        t0 = time.perf_counter()
        ocr_processor = OCRProcessor()
        ocr_result = ocr_processor.process_with_orphans(
            vision_result.objects,
            vision_result.text_blocks,
            debug=self.debug_mode,
        )
        bottle_texts = ocr_result.bottle_texts
        orphaned_texts = ocr_result.orphaned_texts
        timings["ocr_ms"] = round((time.perf_counter() - t0) * 1000)
        logger.info(
            f"TurboPipeline: OCR grouped {len(bottle_texts)} bottles, "
            f"{len(orphaned_texts)} orphans in {timings['ocr_ms']}ms"
        )

        # Stage 3: Fuzzy match + LLM batch validation (NO Claude Vision, NO LLM rescue)
        t0 = time.perf_counter()
        pipeline = RecognitionPipeline(
            wine_matcher=self.wine_matcher,
            use_llm=self.use_llm,
            llm_provider=Config.llm_provider(),
            debug_mode=self.debug_mode,
        )
        recognized = await pipeline.recognize(bottle_texts)
        timings["matching_ms"] = round((time.perf_counter() - t0) * 1000)
        logger.info(
            f"TurboPipeline: Matched {len(recognized)} of {len(bottle_texts)} bottles "
            f"in {timings['matching_ms']}ms"
        )

        timings["total_ms"] = round((time.perf_counter() - total_start) * 1000)
        logger.info(
            f"TurboPipeline: Total {timings['total_ms']}ms "
            f"(vision={timings['vision_ms']}ms, ocr={timings['ocr_ms']}ms, "
            f"matching={timings['matching_ms']}ms)"
        )

        debug_data = None
        if self.debug_mode:
            debug_data = {
                "pipeline_steps": pipeline.debug_steps,
                "llm_call_count": pipeline.llm_call_count,
                "bottles_detected": len(vision_result.objects),
                "bottles_with_text": sum(1 for bt in bottle_texts if bt.combined_text),
            }

        return TurboPipelineResult(
            recognized_wines=recognized,
            fallback=[],  # Populated by the caller after dedup/split
            orphaned_texts=orphaned_texts,
            timings=timings,
            debug_data=debug_data,
        )
