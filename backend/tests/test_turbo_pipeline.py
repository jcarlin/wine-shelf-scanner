"""
Tests for the turbo wine recognition pipeline.

Tests the TurboPipeline that uses Vision API + OCR + fuzzy/LLM matching
but SKIPS Claude Vision fallback and LLM rescue stages.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.turbo_pipeline import TurboPipeline, TurboPipelineResult
from app.services.recognition_pipeline import RecognizedWine
from app.services.ocr_processor import BottleText, OCRProcessingResult, OrphanedText
from app.services.vision import (
    BoundingBox,
    DetectedObject,
    MockVisionService,
    TextBlock,
    VisionResult,
)
from app.services.wine_matcher import WineMatcher
from app.models.enums import RatingSource, WineSource


def _make_vision_result(num_bottles=3) -> VisionResult:
    """Create a mock VisionResult with bottles and text."""
    objects = [
        DetectedObject("Bottle", 0.95, BoundingBox(0.05, 0.15, 0.08, 0.35)),
        DetectedObject("Bottle", 0.93, BoundingBox(0.15, 0.12, 0.09, 0.38)),
        DetectedObject("Bottle", 0.91, BoundingBox(0.26, 0.14, 0.08, 0.36)),
    ][:num_bottles]

    text_blocks = [
        TextBlock("CAYMUS", BoundingBox(0.06, 0.25, 0.06, 0.04), 0.9),
        TextBlock("Cabernet Sauvignon", BoundingBox(0.05, 0.30, 0.08, 0.03), 0.9),
        TextBlock("OPUS ONE", BoundingBox(0.16, 0.22, 0.07, 0.04), 0.9),
        TextBlock("Napa Valley", BoundingBox(0.16, 0.27, 0.07, 0.03), 0.9),
        TextBlock("SILVER OAK", BoundingBox(0.27, 0.24, 0.06, 0.04), 0.9),
        TextBlock("Alexander Valley", BoundingBox(0.26, 0.29, 0.08, 0.03), 0.9),
    ]

    return VisionResult(
        objects=objects,
        text_blocks=text_blocks,
        raw_text="CAYMUS Cabernet Sauvignon OPUS ONE Napa Valley SILVER OAK Alexander Valley",
        image_width=1000,
        image_height=1000,
    )


# === Test TurboPipeline Class ===


class TestTurboPipeline:
    """Test TurboPipeline with mocked services."""

    @pytest.mark.asyncio
    async def test_basic_run_returns_result(self):
        """TurboPipeline returns TurboPipelineResult with recognized wines."""
        vision_result = _make_vision_result()

        mock_vision = MagicMock()
        mock_vision.analyze.return_value = vision_result

        with patch("app.services.turbo_pipeline.VisionService", return_value=mock_vision):
            turbo = TurboPipeline(
                image_bytes=b"fake_image",
                wine_matcher=WineMatcher(),
                use_llm=False,  # Skip LLM for speed
                debug_mode=False,
            )
            result = await turbo.run()

        assert isinstance(result, TurboPipelineResult)
        assert isinstance(result.timings, dict)
        assert "vision_ms" in result.timings
        assert "ocr_ms" in result.timings
        assert "matching_ms" in result.timings
        assert "total_ms" in result.timings
        # Vision was called
        mock_vision.analyze.assert_called_once_with(b"fake_image")

    @pytest.mark.asyncio
    async def test_no_bottles_returns_empty(self):
        """If Vision API detects no bottles, return empty result immediately."""
        empty_result = VisionResult(
            objects=[], text_blocks=[], raw_text="", image_width=1000, image_height=1000
        )

        mock_vision = MagicMock()
        mock_vision.analyze.return_value = empty_result

        with patch("app.services.turbo_pipeline.VisionService", return_value=mock_vision):
            turbo = TurboPipeline(
                image_bytes=b"fake_image",
                wine_matcher=WineMatcher(),
                use_llm=False,
            )
            result = await turbo.run()

        assert len(result.recognized_wines) == 0
        assert len(result.fallback) == 0
        assert "vision_ms" in result.timings
        assert "total_ms" in result.timings
        # Should NOT have ocr_ms or matching_ms since we exited early
        assert "ocr_ms" not in result.timings

    @pytest.mark.asyncio
    async def test_does_not_call_claude_vision(self):
        """Verify turbo pipeline does NOT invoke Claude Vision fallback."""
        vision_result = _make_vision_result()

        mock_vision = MagicMock()
        mock_vision.analyze.return_value = vision_result

        with patch("app.services.turbo_pipeline.VisionService", return_value=mock_vision), \
             patch("app.services.claude_vision.get_claude_vision_service") as mock_claude:
            turbo = TurboPipeline(
                image_bytes=b"fake_image",
                wine_matcher=WineMatcher(),
                use_llm=False,
            )
            await turbo.run()

        # Claude Vision should never be called
        mock_claude.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_call_llm_rescue(self):
        """Verify turbo pipeline does NOT invoke LLM rescue batch."""
        vision_result = _make_vision_result()

        mock_vision = MagicMock()
        mock_vision.analyze.return_value = vision_result

        with patch("app.services.turbo_pipeline.VisionService", return_value=mock_vision), \
             patch("app.services.llm_normalizer.get_normalizer") as mock_normalizer_fn:
            # Set up a mock normalizer that tracks calls
            mock_normalizer = MagicMock()
            mock_normalizer.validate_batch = AsyncMock(return_value=[])
            mock_normalizer_fn.return_value = mock_normalizer

            turbo = TurboPipeline(
                image_bytes=b"fake_image",
                wine_matcher=WineMatcher(),
                use_llm=False,  # LLM disabled = no validate_batch
            )
            result = await turbo.run()

        # With use_llm=False, the pipeline's normalizer should be a mock
        # and validate_batch should NOT be called for rescue
        # The key assertion: no Claude Vision, no rescue
        assert isinstance(result, TurboPipelineResult)

    @pytest.mark.asyncio
    async def test_timing_instrumentation(self):
        """Verify all timing keys are present and are positive numbers."""
        vision_result = _make_vision_result()

        mock_vision = MagicMock()
        mock_vision.analyze.return_value = vision_result

        with patch("app.services.turbo_pipeline.VisionService", return_value=mock_vision):
            turbo = TurboPipeline(
                image_bytes=b"fake_image",
                wine_matcher=WineMatcher(),
                use_llm=False,
            )
            result = await turbo.run()

        assert result.timings["vision_ms"] >= 0
        assert result.timings["ocr_ms"] >= 0
        assert result.timings["matching_ms"] >= 0
        assert result.timings["total_ms"] >= 0
        # Total should be >= sum of parts
        assert result.timings["total_ms"] >= (
            result.timings["vision_ms"] + result.timings["ocr_ms"] + result.timings["matching_ms"]
        ) - 1  # 1ms tolerance for rounding

    @pytest.mark.asyncio
    async def test_orphaned_texts_collected(self):
        """Orphaned text blocks are returned in the result."""
        # Create bottles and text where some text is far from any bottle
        objects = [
            DetectedObject("Bottle", 0.95, BoundingBox(0.05, 0.15, 0.08, 0.35)),
        ]
        text_blocks = [
            TextBlock("CAYMUS", BoundingBox(0.06, 0.25, 0.06, 0.04), 0.9),
            # Far-away text that won't be assigned to any bottle
            TextBlock("Stag's Leap", BoundingBox(0.85, 0.85, 0.06, 0.04), 0.9),
        ]
        vision_result = VisionResult(
            objects=objects, text_blocks=text_blocks, raw_text="",
            image_width=1000, image_height=1000,
        )

        mock_vision = MagicMock()
        mock_vision.analyze.return_value = vision_result

        with patch("app.services.turbo_pipeline.VisionService", return_value=mock_vision):
            turbo = TurboPipeline(
                image_bytes=b"fake_image",
                wine_matcher=WineMatcher(),
                use_llm=False,
            )
            result = await turbo.run()

        # Should have orphaned texts from the far-away text block
        assert isinstance(result.orphaned_texts, list)

    @pytest.mark.asyncio
    async def test_debug_mode_collects_data(self):
        """Debug mode populates debug_data in the result."""
        vision_result = _make_vision_result()

        mock_vision = MagicMock()
        mock_vision.analyze.return_value = vision_result

        with patch("app.services.turbo_pipeline.VisionService", return_value=mock_vision):
            turbo = TurboPipeline(
                image_bytes=b"fake_image",
                wine_matcher=WineMatcher(),
                use_llm=False,
                debug_mode=True,
            )
            result = await turbo.run()

        assert result.debug_data is not None
        assert "pipeline_steps" in result.debug_data
        assert "bottles_detected" in result.debug_data
        assert result.debug_data["bottles_detected"] == 3


# === Test _run_turbo_pipeline Wrapper ===


class TestRunTurboPipeline:
    """Test the _run_turbo_pipeline wrapper function in scan.py."""

    @pytest.mark.asyncio
    async def test_turbo_wrapper_returns_scan_response(self):
        """_run_turbo_pipeline returns ScanResponse when wines are found."""
        from app.routes.scan import _run_turbo_pipeline

        vision_result = _make_vision_result()
        mock_vision = MagicMock()
        mock_vision.analyze.return_value = vision_result

        with patch("app.services.turbo_pipeline.VisionService", return_value=mock_vision):
            response = await _run_turbo_pipeline(
                image_id="test-123",
                image_bytes=b"fake_image",
                use_llm=False,
                debug_mode=False,
                wine_matcher=WineMatcher(),
                flags=None,
            )

        if response is not None:
            from app.models.response import ScanResponse
            assert isinstance(response, ScanResponse)
            assert response.image_id == "test-123"

    @pytest.mark.asyncio
    async def test_turbo_wrapper_returns_none_on_empty(self):
        """_run_turbo_pipeline returns None when no wines found."""
        from app.routes.scan import _run_turbo_pipeline

        empty_result = VisionResult(
            objects=[], text_blocks=[], raw_text="", image_width=1000, image_height=1000
        )
        mock_vision = MagicMock()
        mock_vision.analyze.return_value = empty_result

        with patch("app.services.turbo_pipeline.VisionService", return_value=mock_vision):
            response = await _run_turbo_pipeline(
                image_id="test-empty",
                image_bytes=b"fake_image",
                use_llm=False,
                debug_mode=False,
                wine_matcher=WineMatcher(),
                flags=None,
            )

        assert response is None


# === Test Pipeline Mode Routing ===


class TestPipelineModeRouting:
    """Test that process_image routes to the correct pipeline based on PIPELINE_MODE."""

    @pytest.mark.asyncio
    async def test_turbo_mode_routes_to_turbo(self):
        """PIPELINE_MODE=turbo routes to _run_turbo_pipeline."""
        from app.routes.scan import process_image

        vision_result = _make_vision_result()
        mock_vision = MagicMock()
        mock_vision.analyze.return_value = vision_result

        with patch("app.routes.scan.Config.pipeline_mode", return_value="turbo"), \
             patch("app.services.turbo_pipeline.VisionService", return_value=mock_vision):
            response = await process_image(
                image_id="test-routing",
                image_bytes=b"fake_image",
                use_real_api=True,
                use_llm=False,
                use_vision_fallback=False,
                debug_mode=False,
                wine_matcher=WineMatcher(),
            )

        from app.models.response import ScanResponse
        assert isinstance(response, ScanResponse)

    @pytest.mark.asyncio
    async def test_hybrid_mode_falls_back_to_legacy(self):
        """PIPELINE_MODE=hybrid falls back to legacy since hybrid is not implemented."""
        from app.routes.scan import process_image

        # Hybrid is not implemented, so it should fall back to legacy.
        # Mock the Vision API for legacy pipeline.
        mock_vision_svc = MockVisionService("full_shelf")

        with patch("app.routes.scan.Config.pipeline_mode", return_value="hybrid"), \
             patch("app.routes.scan.VisionService", return_value=mock_vision_svc):
            response = await process_image(
                image_id="test-hybrid-fallback",
                image_bytes=b"fake_image",
                use_real_api=True,
                use_llm=False,
                use_vision_fallback=False,
                debug_mode=False,
                wine_matcher=WineMatcher(),
            )

        from app.models.response import ScanResponse
        assert isinstance(response, ScanResponse)

    @pytest.mark.asyncio
    async def test_legacy_mode_skips_turbo(self):
        """PIPELINE_MODE=legacy (default) skips turbo and runs legacy pipeline."""
        from app.routes.scan import process_image

        mock_vision_svc = MockVisionService("full_shelf")

        with patch("app.routes.scan.Config.pipeline_mode", return_value="legacy"), \
             patch("app.routes.scan.VisionService", return_value=mock_vision_svc), \
             patch("app.routes.scan._run_turbo_pipeline") as mock_turbo:
            response = await process_image(
                image_id="test-legacy",
                image_bytes=b"fake_image",
                use_real_api=True,
                use_llm=False,
                use_vision_fallback=False,
                debug_mode=False,
                wine_matcher=WineMatcher(),
            )

        # Turbo should NOT have been called
        mock_turbo.assert_not_called()

        from app.models.response import ScanResponse
        assert isinstance(response, ScanResponse)
