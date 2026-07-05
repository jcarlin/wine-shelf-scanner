"""
Tests for the Detect+Read core (detect_read.py) and its production pipeline
wiring — currently the input-quality gate (median detected bottle width).

The gate runs after detection (boxes are known before any LLM spend) and
must be opt-in: the eval harness calls run_detect_read without min_bottle_px
and measures low-res images deliberately.
"""

import io
import json
import pytest
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.services.detect_read import run_detect_read, DetectReadResult


def _jpeg(width: int = 1000, height: int = 800) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (40, 20, 20)).save(buf, format="JPEG")
    return buf.getvalue()


def _boxes(widths_px: list[float], image_width: int = 1000) -> list[dict]:
    """Detection boxes with the given pixel widths on an image_width-px image."""
    boxes = []
    for i, w_px in enumerate(widths_px):
        boxes.append({
            "x": min(0.9, 0.05 + i * 0.12),
            "y": 0.2,
            "w": w_px / image_width,
            "h": 0.5,
            "conf": 0.9,
        })
    return boxes


class TestInputQualityGate:
    """run_detect_read(min_bottle_px=...) rejects low-res shelves before LLM spend."""

    @pytest.mark.asyncio
    async def test_below_floor_skips_llm_and_flags_low_quality(self):
        """Median bottle width below the floor: no LLM call, low_quality set."""
        with patch(
            "app.services.detect_read.detect_bottles",
            return_value=_boxes([80, 90, 100, 70, 85]),
        ), patch(
            "app.services.detect_read._llm_call",
            new=AsyncMock(side_effect=AssertionError("LLM must not be called below the floor")),
        ):
            result = await run_detect_read(_jpeg(1000), "anthropic/claude-sonnet-5",
                                           min_bottle_px=140)

        assert result.low_quality is True
        assert result.predictions == []
        assert result.median_bottle_px == pytest.approx(85, abs=1)
        assert result.bottles_detected == 5
        # Only the vision detection call is in usage — no LLM spend.
        assert [u["call"] for u in result.usage] == ["vision_detect"]

    @pytest.mark.asyncio
    async def test_above_floor_proceeds_to_reads(self):
        """Median width above the floor: reads happen, low_quality stays False."""
        llm_response = json.dumps([[0, "Caymus Cabernet Sauvignon", 0.9, 4.3],
                                   [1, "Opus One", 0.85, 4.6]])
        with patch(
            "app.services.detect_read.detect_bottles",
            return_value=_boxes([200, 220]),
        ), patch(
            "app.services.detect_read._llm_call",
            new=AsyncMock(return_value=llm_response),
        ):
            result = await run_detect_read(_jpeg(1000), "anthropic/claude-sonnet-5",
                                           min_bottle_px=140)

        assert result.low_quality is False
        assert len(result.predictions) == 2
        assert result.median_bottle_px == pytest.approx(210, abs=1)

    @pytest.mark.asyncio
    async def test_no_floor_means_no_gating(self):
        """Default (min_bottle_px=None) preserves harness behavior on tiny boxes."""
        llm_response = json.dumps([[0, "Tiny Label Wine", 0.7, 3.9]])
        with patch(
            "app.services.detect_read.detect_bottles",
            return_value=_boxes([60, 70, 80]),
        ), patch(
            "app.services.detect_read._llm_call",
            new=AsyncMock(return_value=llm_response),
        ):
            result = await run_detect_read(_jpeg(1000), "anthropic/claude-sonnet-5")

        assert result.low_quality is False
        assert len(result.predictions) == 1


class TestDetectBottlesDegenerateInputs:
    """Tiny images must not crash detection (tiles collapse to zero size)."""

    def test_1x1_image_returns_no_boxes(self):
        from unittest.mock import MagicMock
        import app.services.detect_read as dr

        client = MagicMock()
        client.object_localization.return_value.localized_object_annotations = []
        with patch.object(dr, "_get_vision_client", return_value=client):
            assert dr.detect_bottles(Image.new("RGB", (1, 1))) == []


class TestPipelineQualitySignal:
    """DetectReadPipeline surfaces the gate as SingleLLMResult.scan_quality."""

    @pytest.mark.asyncio
    async def test_low_quality_result_maps_to_scan_quality(self):
        from app.services.detect_read_pipeline import DetectReadPipeline

        gated = DetectReadResult(
            predictions=[], usage=[], notes="low_resolution",
            median_bottle_px=92.0, bottles_detected=14, low_quality=True,
        )
        pipeline = DetectReadPipeline(wine_matcher=None, use_llm_cache=False)
        with patch("app.services.detect_read_pipeline.run_detect_read",
                   new=AsyncMock(return_value=gated)):
            result = await pipeline.scan(_jpeg(1000), image_id="test-img")

        assert result.recognized_wines == []
        assert result.scan_quality == {
            "status": "low_resolution",
            "median_bottle_px": 92,
            "bottles_detected": 14,
        }

    @pytest.mark.asyncio
    async def test_normal_result_has_no_scan_quality(self):
        from app.services.detect_read_pipeline import DetectReadPipeline

        ok = DetectReadResult(
            predictions=[], usage=[], notes="no bottles detected",
        )
        pipeline = DetectReadPipeline(wine_matcher=None, use_llm_cache=False)
        with patch("app.services.detect_read_pipeline.run_detect_read",
                   new=AsyncMock(return_value=ok)):
            result = await pipeline.scan(_jpeg(1000), image_id="test-img")

        assert result.scan_quality is None


class TestScanQualityResponseModel:
    """ScanResponse carries the optional scan_quality field (additive; iOS-safe)."""

    def test_scan_quality_round_trip(self):
        from app.models import ScanResponse
        from app.models.response import ScanQuality

        resp = ScanResponse(
            image_id="abc",
            results=[],
            fallback_list=[],
            scan_quality=ScanQuality(
                status="low_resolution", median_bottle_px=92, bottles_detected=14,
            ),
        )
        data = resp.model_dump()
        assert data["scan_quality"]["status"] == "low_resolution"

    def test_scan_quality_defaults_to_none(self):
        from app.models import ScanResponse

        resp = ScanResponse(image_id="abc", results=[], fallback_list=[])
        assert resp.model_dump()["scan_quality"] is None
