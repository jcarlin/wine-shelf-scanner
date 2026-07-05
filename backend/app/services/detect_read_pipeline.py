"""
Detect + Read production pipeline (PIPELINE_MODE=detect_read).

Tiled Google Vision detection supplies bottle boxes; Claude reads each
bottle's label from a per-bottle crop. The LLM never emits coordinates,
which eliminates the bbox-quality problems of the single-LLM pipeline
(see docs/FEASIBILITY_RUN_LOG.md, Gate 2).

Reuses SingleLLMPipeline's DB cross-match (canonical name + rating override)
and LLM-rating-cache behavior; only the recognition step differs. Core
recognition logic lives in detect_read.py and is shared with the eval
harness so measurements cover the shipping code. No fallback to other
pipelines — errors propagate.

scan() is the non-streaming entry point (POST /scan). scan_stream() yields
a DB-matched SingleLLMResult snapshot as each parallel crop-read chunk
completes (POST /scan/stream); the final snapshot is identical to what
scan() returns.
"""

import logging
import time

from ..config import Config
from .detect_read import DetectReadResult, run_detect_read, run_detect_read_stream
from .llm_usage import log_usage
from .single_llm_pipeline import SingleLLMPipeline, SingleLLMResult, SingleLLMWine

logger = logging.getLogger(__name__)


class DetectReadPipeline(SingleLLMPipeline):
    """Vision-detected boxes + Claude label reads, DB-matched like single_llm."""

    def _select_model(self) -> str:
        return self._configured_model or Config.detect_read_model()

    def _min_bottle_px(self):
        min_px = Config.detect_read_min_bottle_px()
        return min_px if min_px > 0 else None

    def _log_result_usage(self, result: DetectReadResult, image_id: str) -> None:
        for u in result.usage:
            if u.get("prompt_tokens") is None and u.get("completion_tokens") is None:
                continue  # vision call; cost surfaces via timings["cost_usd"]
            log_usage(
                image_id=image_id,
                model=u["model"],
                prompt_tokens=u.get("prompt_tokens"),
                completion_tokens=u.get("completion_tokens"),
                cached_tokens=None,
                latency_ms=u.get("latency_ms") or 0,
                truncated=bool(u.get("truncated")),
                log_path=Config.token_usage_log_path(),
            )

    @staticmethod
    def _to_llm_wines(result: DetectReadResult) -> list[SingleLLMWine]:
        return [
            SingleLLMWine(
                wine_name=p.wine_name,
                confidence=p.confidence,
                estimated_rating=p.rating,
                bbox={
                    "x": p.bbox["x"],
                    "y": p.bbox["y"],
                    "width": p.bbox["w"],
                    "height": p.bbox["h"],
                },
            )
            for p in result.predictions
        ]

    @staticmethod
    def _to_scan_quality(result: DetectReadResult):
        if not result.low_quality:
            return None
        return {
            "status": "low_resolution",
            "median_bottle_px": round(result.median_bottle_px),
            "bottles_detected": result.bottles_detected,
        }

    def _finalize(self, result: DetectReadResult, timings: dict,
                  image_id: str, model: str, total_start: float) -> SingleLLMResult:
        """Shared final-result handling for scan() and scan_stream()."""
        timings["detect_read_ms"] = round((time.perf_counter() - total_start) * 1000)
        timings["cost_usd"] = round(result.total_cost_usd, 6)
        timings["notes"] = result.notes

        scan_quality = self._to_scan_quality(result)
        if scan_quality:
            logger.info(
                f"DetectReadPipeline: input-quality gate rejected scan "
                f"({result.notes})"
            )

        self._log_result_usage(result, image_id)

        llm_wines = self._to_llm_wines(result)
        if not llm_wines:
            timings["total_ms"] = round((time.perf_counter() - total_start) * 1000)
            return SingleLLMResult(recognized_wines=[], raw_llm_wines=[],
                                   timings=timings, scan_quality=scan_quality)

        t0 = time.perf_counter()
        recognized = self._match_against_db(llm_wines)
        timings["db_lookup_ms"] = round((time.perf_counter() - t0) * 1000)
        self._cache_llm_wines(recognized, model)

        timings["total_ms"] = round((time.perf_counter() - total_start) * 1000)
        logger.info(
            f"DetectReadPipeline: {len(recognized)} wines in {timings['total_ms']}ms "
            f"(${timings['cost_usd']:.4f}, {result.notes})"
        )
        return SingleLLMResult(
            recognized_wines=recognized,
            raw_llm_wines=llm_wines,
            timings=timings,
            scan_quality=scan_quality,
        )

    async def scan(
        self,
        image_bytes: bytes,
        image_media_type: str = "image/jpeg",
        image_id: str = "",
    ) -> SingleLLMResult:
        timings: dict = {}
        total_start = time.perf_counter()
        model = self._select_model()
        timings["model"] = model

        result = await run_detect_read(
            image_bytes, model, call_label="detect_read",
            min_bottle_px=self._min_bottle_px(),
        )
        return self._finalize(result, timings, image_id, model, total_start)

    async def scan_stream(
        self,
        image_bytes: bytes,
        image_media_type: str = "image/jpeg",
        image_id: str = "",
    ):
        """Async generator: yields a DB-matched SingleLLMResult per completed
        crop-read chunk (partial=True), then the final result (partial=False,
        identical to scan())."""
        total_start = time.perf_counter()
        model = self._select_model()

        async for result in run_detect_read_stream(
            image_bytes, model, call_label="detect_read",
            min_bottle_px=self._min_bottle_px(),
        ):
            if result.partial:
                llm_wines = self._to_llm_wines(result)
                recognized = self._match_against_db(llm_wines) if llm_wines else []
                yield SingleLLMResult(
                    recognized_wines=recognized,
                    raw_llm_wines=llm_wines,
                    timings={
                        "model": model,
                        "notes": result.notes,
                        "partial_ms": round((time.perf_counter() - total_start) * 1000),
                    },
                    partial=True,
                )
            else:
                yield self._finalize(result, {"model": model}, image_id,
                                     model, total_start)
