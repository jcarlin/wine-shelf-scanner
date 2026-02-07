"""Tests for the hybrid pipeline (Vision API + Gemini Flash in parallel)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.hybrid_pipeline import (
    HybridPipeline,
    HybridPipelineResult,
    _compute_iou,
    _bbox_to_dict,
)
from app.services.fast_pipeline import FastPipelineWine
from app.services.recognition_pipeline import RecognizedWine
from app.services.vision import BoundingBox, DetectedObject, TextBlock, VisionResult
from app.services.ocr_processor import BottleText
from app.models.enums import RatingSource, WineSource


# ──────────────────────────────────────────────────
# IoU tests
# ──────────────────────────────────────────────────

class TestComputeIoU:
    def test_identical_boxes(self):
        box = {'x': 0.1, 'y': 0.2, 'width': 0.3, 'height': 0.4}
        assert _compute_iou(box, box) == pytest.approx(1.0)

    def test_no_overlap(self):
        box1 = {'x': 0.0, 'y': 0.0, 'width': 0.1, 'height': 0.1}
        box2 = {'x': 0.5, 'y': 0.5, 'width': 0.1, 'height': 0.1}
        assert _compute_iou(box1, box2) == 0.0

    def test_partial_overlap(self):
        box1 = {'x': 0.0, 'y': 0.0, 'width': 0.2, 'height': 0.2}
        box2 = {'x': 0.1, 'y': 0.1, 'width': 0.2, 'height': 0.2}
        # Intersection: 0.1 * 0.1 = 0.01
        # Union: 0.04 + 0.04 - 0.01 = 0.07
        expected = 0.01 / 0.07
        assert _compute_iou(box1, box2) == pytest.approx(expected, abs=1e-6)

    def test_contained_box(self):
        outer = {'x': 0.0, 'y': 0.0, 'width': 1.0, 'height': 1.0}
        inner = {'x': 0.2, 'y': 0.2, 'width': 0.1, 'height': 0.1}
        # Intersection = inner area = 0.01
        # Union = 1.0 + 0.01 - 0.01 = 1.0
        expected = 0.01 / 1.0
        assert _compute_iou(outer, inner) == pytest.approx(expected)

    def test_edge_touching_no_overlap(self):
        box1 = {'x': 0.0, 'y': 0.0, 'width': 0.5, 'height': 0.5}
        box2 = {'x': 0.5, 'y': 0.0, 'width': 0.5, 'height': 0.5}
        assert _compute_iou(box1, box2) == 0.0

    def test_zero_area_box(self):
        box1 = {'x': 0.0, 'y': 0.0, 'width': 0.0, 'height': 0.0}
        box2 = {'x': 0.0, 'y': 0.0, 'width': 0.1, 'height': 0.1}
        assert _compute_iou(box1, box2) == 0.0


class TestBboxToDict:
    def test_conversion(self):
        bbox = BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4)
        result = _bbox_to_dict(bbox)
        assert result == {'x': 0.1, 'y': 0.2, 'width': 0.3, 'height': 0.4}


# ──────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────

def _make_vision_result(num_bottles=3) -> VisionResult:
    """Create a mock VisionResult with evenly-spaced bottles and text."""
    objects = []
    text_blocks = []
    names = ["CAYMUS", "OPUS ONE", "SILVER OAK"]

    for i in range(min(num_bottles, len(names))):
        x = 0.1 + i * 0.3
        objects.append(DetectedObject(
            name="Bottle",
            confidence=0.9,
            bbox=BoundingBox(x=x, y=0.15, width=0.1, height=0.35),
        ))
        text_blocks.append(TextBlock(
            text=names[i],
            bbox=BoundingBox(x=x + 0.01, y=0.25, width=0.08, height=0.04),
            confidence=0.9,
        ))

    return VisionResult(
        objects=objects,
        text_blocks=text_blocks,
        raw_text=" ".join(names[:num_bottles]),
        image_width=1000,
        image_height=1000,
    )


def _make_gemini_wines(num=3) -> list[FastPipelineWine]:
    """Create mock Gemini wines with matching bboxes."""
    wines_data = [
        ("Caymus Cabernet Sauvignon", 4.5, 0.1),
        ("Opus One 2019", 4.7, 0.4),
        ("Silver Oak Alexander Valley", 4.3, 0.7),
    ]
    wines = []
    for i in range(min(num, len(wines_data))):
        name, rating, x = wines_data[i]
        wines.append(FastPipelineWine(
            wine_name=name,
            confidence=0.85,
            estimated_rating=rating,
            bbox={'x': x, 'y': 0.15, 'width': 0.1, 'height': 0.35},
            wine_type="Red",
            brand=name.split()[0],
            region="Napa Valley",
            varietal="Cabernet Sauvignon",
            blurb="A fine wine.",
        ))
    return wines


def _make_mock_matcher():
    """Create a WineMatcher mock that returns None for any match."""
    matcher = MagicMock()
    matcher.match.return_value = None
    return matcher


# ──────────────────────────────────────────────────
# Pipeline tests
# ──────────────────────────────────────────────────

class TestHybridPipelineBothSucceed:
    """Tests for when both Vision API and Gemini succeed."""

    @pytest.mark.asyncio
    async def test_both_succeed_merges_by_iou(self):
        vision_result = _make_vision_result(3)
        gemini_wines = _make_gemini_wines(3)

        pipeline = HybridPipeline(
            wine_matcher=_make_mock_matcher(),
            use_llm_cache=False,
        )

        with patch.object(pipeline, '_run_vision', return_value=vision_result), \
             patch.object(pipeline, '_run_gemini', new_callable=AsyncMock, return_value=gemini_wines):

            result = await pipeline.scan(b"fake_image")

        assert isinstance(result, HybridPipelineResult)
        assert len(result.recognized_wines) == 3
        assert 'total_ms' in result.timings
        assert 'merge_ms' in result.timings
        assert 'db_lookup_ms' in result.timings

        # All wines should use Gemini names (not OCR text)
        wine_names = {w.wine_name for w in result.recognized_wines}
        assert "Caymus Cabernet Sauvignon" in wine_names
        assert "Opus One 2019" in wine_names
        assert "Silver Oak Alexander Valley" in wine_names

    @pytest.mark.asyncio
    async def test_gemini_no_iou_match_falls_to_fallback(self):
        """Gemini wine with non-overlapping bbox goes to fallback."""
        vision_result = _make_vision_result(1)  # One bottle at x=0.1
        gemini_wines = [FastPipelineWine(
            wine_name="Far Away Wine",
            confidence=0.8,
            estimated_rating=4.0,
            bbox={'x': 0.9, 'y': 0.9, 'width': 0.05, 'height': 0.05},  # No overlap
        )]

        pipeline = HybridPipeline(
            wine_matcher=_make_mock_matcher(),
            use_llm_cache=False,
        )

        with patch.object(pipeline, '_run_vision', return_value=vision_result), \
             patch.object(pipeline, '_run_gemini', new_callable=AsyncMock, return_value=gemini_wines):

            result = await pipeline.scan(b"fake_image")

        # Gemini wine should be in fallback (no matching Vision bbox)
        assert len(result.fallback) == 1
        assert result.fallback[0]['wine_name'] == "Far Away Wine"


class TestHybridPipelineVisionOnly:
    """Tests for when only Vision API succeeds (Gemini fails)."""

    @pytest.mark.asyncio
    async def test_vision_only_falls_back_to_fuzzy_match(self):
        vision_result = _make_vision_result(1)

        matcher = _make_mock_matcher()
        # Make fuzzy match return a result for CAYMUS
        from app.services.wine_matcher import WineMatch
        matcher.match.return_value = WineMatch(
            canonical_name="Caymus Cabernet Sauvignon",
            rating=4.5,
            confidence=0.88,
            source="fts",
            wine_type="Red",
            brand="Caymus",
            region="Napa Valley",
            varietal="Cabernet Sauvignon",
        )

        pipeline = HybridPipeline(
            wine_matcher=matcher,
            use_llm_cache=False,
        )

        with patch.object(pipeline, '_run_vision', return_value=vision_result), \
             patch.object(pipeline, '_run_gemini', new_callable=AsyncMock, return_value=[]):

            result = await pipeline.scan(b"fake_image")

        assert len(result.recognized_wines) == 1
        assert result.recognized_wines[0].wine_name == "Caymus Cabernet Sauvignon"
        assert result.recognized_wines[0].source == WineSource.DATABASE


class TestHybridPipelineGeminiOnly:
    """Tests for when only Gemini succeeds (Vision API fails)."""

    @pytest.mark.asyncio
    async def test_gemini_only_uses_gemini_bboxes(self):
        gemini_wines = _make_gemini_wines(2)

        pipeline = HybridPipeline(
            wine_matcher=_make_mock_matcher(),
            use_llm_cache=False,
        )

        with patch.object(pipeline, '_run_vision', side_effect=Exception("Vision API down")), \
             patch.object(pipeline, '_run_gemini', new_callable=AsyncMock, return_value=gemini_wines):

            result = await pipeline.scan(b"fake_image")

        assert len(result.recognized_wines) == 2
        # Source should be LLM since no DB match
        for wine in result.recognized_wines:
            assert wine.source == WineSource.LLM


class TestHybridPipelineBothFail:
    """Tests for when both Vision and Gemini fail."""

    @pytest.mark.asyncio
    async def test_both_fail_returns_empty(self):
        pipeline = HybridPipeline(
            wine_matcher=_make_mock_matcher(),
            use_llm_cache=False,
        )

        with patch.object(pipeline, '_run_vision', side_effect=Exception("fail")), \
             patch.object(pipeline, '_run_gemini', new_callable=AsyncMock, side_effect=Exception("fail")):

            result = await pipeline.scan(b"fake_image")

        assert result.recognized_wines == []
        assert result.fallback == []
        assert 'total_ms' in result.timings


class TestDBValidation:
    """Tests for DB cross-referencing."""

    @pytest.mark.asyncio
    async def test_db_match_upgrades_source(self):
        """LLM wine should get upgraded to DATABASE when DB match is found."""
        gemini_wines = _make_gemini_wines(1)

        from app.services.wine_matcher import WineMatch
        matcher = _make_mock_matcher()
        matcher.match.return_value = WineMatch(
            canonical_name="Caymus Cabernet Sauvignon Napa Valley",
            rating=4.6,
            confidence=0.92,
            source="fts",
            wine_type="Red",
            brand="Caymus",
            region="Napa Valley",
            varietal="Cabernet Sauvignon",
            wine_id=42,
        )

        pipeline = HybridPipeline(
            wine_matcher=matcher,
            use_llm_cache=False,
        )

        with patch.object(pipeline, '_run_vision', side_effect=Exception("fail")), \
             patch.object(pipeline, '_run_gemini', new_callable=AsyncMock, return_value=gemini_wines):

            result = await pipeline.scan(b"fake_image")

        assert len(result.recognized_wines) == 1
        wine = result.recognized_wines[0]
        assert wine.source == WineSource.DATABASE
        assert wine.rating == 4.6  # DB rating, not LLM estimate
        assert wine.wine_name == "Caymus Cabernet Sauvignon Napa Valley"
        assert wine.wine_id == 42


class TestTimingInstrumentation:
    """Tests for timing data in results."""

    @pytest.mark.asyncio
    async def test_timings_present(self):
        pipeline = HybridPipeline(
            wine_matcher=_make_mock_matcher(),
            use_llm_cache=False,
        )

        vision_result = _make_vision_result(1)
        gemini_wines = _make_gemini_wines(1)

        with patch.object(pipeline, '_run_vision', return_value=vision_result), \
             patch.object(pipeline, '_run_gemini', new_callable=AsyncMock, return_value=gemini_wines):

            result = await pipeline.scan(b"fake_image")

        assert 'total_ms' in result.timings
        assert 'merge_ms' in result.timings
        assert 'db_lookup_ms' in result.timings
        # All timings should be non-negative numbers
        for key, val in result.timings.items():
            assert isinstance(val, (int, float))
            assert val >= 0
