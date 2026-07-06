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


class TestDetectReadStream:
    """run_detect_read_stream yields cumulative snapshots per completed chunk,
    then a final post-rescue result identical to what run_detect_read returns."""

    @pytest.mark.asyncio
    async def test_yields_cumulative_snapshots_then_final(self):
        import asyncio
        from app.services.detect_read import run_detect_read_stream

        async def fake_read_crops(model, img, boxes, ids, zone, usage, call_label):
            # First chunk (contains id 0) returns fast; second chunk slower.
            await asyncio.sleep(0.01 if 0 in ids else 0.05)
            return {i: (f"Wine {i}", 0.9, 4.0) for i in ids}

        with patch(
            "app.services.detect_read.detect_bottles",
            return_value=_boxes([200] * 12, image_width=4000),
        ), patch(
            "app.services.detect_read._read_crops",
            new=AsyncMock(side_effect=fake_read_crops),
        ):
            snapshots = [
                s async for s in run_detect_read_stream(
                    _jpeg(4000), "anthropic/claude-sonnet-5")
            ]

        # 12 boxes -> 2 chunks of 10/2 -> 2 chunk snapshots + 1 final.
        assert len(snapshots) == 3
        assert len(snapshots[0].predictions) == 10   # fast chunk first
        assert len(snapshots[1].predictions) == 12   # cumulative
        assert len(snapshots[-1].predictions) == 12  # final, post-rescue
        assert snapshots[-1].bottles_detected == 12
        # Non-final snapshots are marked partial so callers can tell.
        assert snapshots[0].partial is True
        assert snapshots[-1].partial is False

    @pytest.mark.asyncio
    async def test_final_snapshot_matches_run_detect_read(self):
        from app.services.detect_read import run_detect_read, run_detect_read_stream

        async def fake_read_crops(model, img, boxes, ids, zone, usage, call_label):
            return {i: (f"Wine {i}", 0.9, 4.0) for i in ids}

        patches = dict(
            detect=_boxes([200] * 5, image_width=4000),
        )
        with patch(
            "app.services.detect_read.detect_bottles", return_value=patches["detect"],
        ), patch(
            "app.services.detect_read._read_crops",
            new=AsyncMock(side_effect=fake_read_crops),
        ):
            final = None
            async for final in run_detect_read_stream(
                    _jpeg(4000), "anthropic/claude-sonnet-5"):
                pass
            direct = await run_detect_read(_jpeg(4000), "anthropic/claude-sonnet-5")

        assert [p.wine_name for p in final.predictions] == \
            [p.wine_name for p in direct.predictions]

    @pytest.mark.asyncio
    async def test_gated_scan_yields_single_low_quality_snapshot(self):
        from app.services.detect_read import run_detect_read_stream

        with patch(
            "app.services.detect_read.detect_bottles",
            return_value=_boxes([80, 90, 100], image_width=1000),
        ), patch(
            "app.services.detect_read._read_crops",
            new=AsyncMock(side_effect=AssertionError("no reads below the floor")),
        ):
            snapshots = [
                s async for s in run_detect_read_stream(
                    _jpeg(1000), "anthropic/claude-sonnet-5", min_bottle_px=140)
            ]

        assert len(snapshots) == 1
        assert snapshots[0].low_quality is True
        assert snapshots[0].partial is False


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


class TestPipelineScanStream:
    """DetectReadPipeline.scan_stream yields DB-matched snapshots per chunk."""

    @pytest.mark.asyncio
    async def test_yields_partial_then_final(self):
        from app.services.detect_read import DetectReadPrediction
        from app.services.detect_read_pipeline import DetectReadPipeline

        def pred(name):
            return DetectReadPrediction(
                wine_name=name, bbox={"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.5},
                confidence=0.9, rating=4.0)

        async def fake_stream(image_bytes, model, call_label="detect_read",
                              min_bottle_px=None):
            yield DetectReadResult(predictions=[pred("Opus One")], usage=[],
                                   notes="partial chunks=1/2", partial=True)
            yield DetectReadResult(
                predictions=[pred("Opus One"), pred("Caymus Cabernet Sauvignon")],
                usage=[], notes="detected=2 chunks=2 rescued=0 deduped=0")

        pipeline = DetectReadPipeline(wine_matcher=None, use_llm_cache=False)
        with patch("app.services.detect_read_pipeline.run_detect_read_stream",
                   new=fake_stream):
            results = [r async for r in pipeline.scan_stream(_jpeg(), image_id="t")]

        assert len(results) == 2
        assert results[0].partial is True
        assert len(results[0].recognized_wines) == 1
        assert results[1].partial is False
        assert len(results[1].recognized_wines) == 2


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
