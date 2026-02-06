"""
Tests for the fast single-pass wine recognition pipeline.

Tests the FastPipeline that uses Gemini Flash Vision for single-call
wine detection + identification, replacing the multi-stage legacy pipeline.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.fast_pipeline import (
    FastPipeline,
    FastPipelineWine,
    FastPipelineResult,
    _parse_llm_response,
)
from app.services.recognition_pipeline import RecognizedWine
from app.services.wine_matcher import WineMatcher, WineMatch
from app.services.ocr_processor import BottleText
from app.services.vision import DetectedObject, BoundingBox
from app.models.enums import RatingSource, WineSource


# === Test Response Parsing ===


class TestFastPipelineResponseParsing:
    """Test _parse_llm_response() JSON parsing and filtering."""

    def test_parse_valid_response(self):
        """Valid JSON array with wine objects parses correctly."""
        response = json.dumps([
            {
                "wine_name": "Caymus Cabernet Sauvignon",
                "confidence": 0.9,
                "estimated_rating": 4.3,
                "bbox": {"x": 0.1, "y": 0.2, "width": 0.1, "height": 0.4},
                "wine_type": "Red",
                "brand": "Caymus",
                "region": "Napa Valley",
                "varietal": "Cabernet Sauvignon",
                "blurb": "Rich and full-bodied",
            },
            {
                "wine_name": "Opus One",
                "confidence": 0.85,
                "estimated_rating": 4.6,
                "bbox": {"x": 0.3, "y": 0.1, "width": 0.12, "height": 0.5},
            },
        ])

        results = _parse_llm_response(response)

        assert len(results) == 2
        assert results[0].wine_name == "Caymus Cabernet Sauvignon"
        assert results[0].confidence == 0.9
        assert results[0].estimated_rating == 4.3
        assert results[0].bbox == {"x": 0.1, "y": 0.2, "width": 0.1, "height": 0.4}
        assert results[0].wine_type == "Red"
        assert results[0].varietal == "Cabernet Sauvignon"

        assert results[1].wine_name == "Opus One"
        assert results[1].estimated_rating == 4.6

    def test_parse_response_with_markdown(self):
        """Handle ```json code blocks wrapping the response."""
        response = '```json\n[{"wine_name": "Caymus", "confidence": 0.8, "estimated_rating": 4.0, "bbox": {"x": 0, "y": 0, "width": 0.1, "height": 0.3}}]\n```'

        results = _parse_llm_response(response)

        assert len(results) == 1
        assert results[0].wine_name == "Caymus"

    def test_parse_response_with_null_wines(self):
        """Entries with null wine_name are filtered out."""
        response = json.dumps([
            {
                "wine_name": "Caymus",
                "confidence": 0.8,
                "estimated_rating": 4.0,
                "bbox": {"x": 0, "y": 0, "width": 0.1, "height": 0.3},
            },
            {
                "wine_name": None,
                "confidence": 0.3,
                "estimated_rating": None,
                "bbox": {"x": 0.5, "y": 0.1, "width": 0.1, "height": 0.3},
            },
        ])

        results = _parse_llm_response(response)

        assert len(results) == 1
        assert results[0].wine_name == "Caymus"

    def test_parse_invalid_json(self):
        """Invalid JSON returns empty list, no crash."""
        results = _parse_llm_response("this is not json at all")
        assert results == []

    def test_parse_empty_array(self):
        """Empty JSON array returns empty list."""
        results = _parse_llm_response("[]")
        assert results == []

    def test_parse_non_array_json(self):
        """JSON object (not array) returns empty list."""
        results = _parse_llm_response('{"wine_name": "test"}')
        assert results == []

    def test_parse_clamps_rating(self):
        """Ratings are clamped to 1.0-5.0 range."""
        response = json.dumps([
            {
                "wine_name": "Over Rated",
                "confidence": 0.8,
                "estimated_rating": 7.5,
                "bbox": {"x": 0, "y": 0, "width": 0.1, "height": 0.3},
            },
            {
                "wine_name": "Under Rated",
                "confidence": 0.8,
                "estimated_rating": -1.0,
                "bbox": {"x": 0.5, "y": 0, "width": 0.1, "height": 0.3},
            },
        ])

        results = _parse_llm_response(response)

        assert results[0].estimated_rating == 5.0
        assert results[1].estimated_rating == 1.0

    def test_parse_missing_bbox(self):
        """Missing bbox defaults to zeros."""
        response = json.dumps([
            {
                "wine_name": "No Bbox Wine",
                "confidence": 0.7,
                "estimated_rating": 3.8,
            },
        ])

        results = _parse_llm_response(response)

        assert len(results) == 1
        assert results[0].bbox == {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}

    def test_parse_default_confidence(self):
        """Missing confidence defaults to 0.5."""
        response = json.dumps([
            {
                "wine_name": "No Conf Wine",
                "estimated_rating": 3.8,
                "bbox": {"x": 0, "y": 0, "width": 0.1, "height": 0.3},
            },
        ])

        results = _parse_llm_response(response)

        assert len(results) == 1
        assert results[0].confidence == 0.5


# === Test DB Matching ===


class TestFastPipelineDBMatching:
    """Test _match_against_db() DB cross-referencing logic."""

    @pytest.fixture
    def pipeline(self):
        """Create pipeline with real WineMatcher (uses sqlite DB)."""
        return FastPipeline(
            wine_matcher=WineMatcher(),
            use_llm_cache=False,
        )

    def test_db_match_uses_authoritative_rating(self, pipeline):
        """When wine is found in DB with high confidence, use DB rating."""
        llm_wine = FastPipelineWine(
            wine_name="Opus One",
            confidence=0.9,
            estimated_rating=4.5,  # LLM estimate
            bbox={"x": 0.1, "y": 0.2, "width": 0.1, "height": 0.4},
        )

        results = pipeline._match_against_db([llm_wine])

        assert len(results) == 1
        assert results[0].source == WineSource.DATABASE
        assert results[0].rating_source == RatingSource.DATABASE
        # DB rating should be used, not the LLM estimate
        assert results[0].rating is not None
        assert 3.5 <= results[0].rating <= 5.0
        assert results[0].wine_name == "Opus One"

    def test_no_db_match_uses_llm_rating(self, pipeline):
        """When wine is NOT in DB, use LLM estimated rating with capped confidence."""
        llm_wine = FastPipelineWine(
            wine_name="Totally Unknown Boutique Wine XYZ",
            confidence=0.85,
            estimated_rating=4.1,
            bbox={"x": 0.1, "y": 0.2, "width": 0.1, "height": 0.4},
        )

        results = pipeline._match_against_db([llm_wine])

        assert len(results) == 1
        assert results[0].source == WineSource.LLM
        assert results[0].rating_source == RatingSource.LLM_ESTIMATED
        assert results[0].rating == 4.1
        assert results[0].wine_name == "Totally Unknown Boutique Wine XYZ"

    def test_confidence_capping_with_rating(self, pipeline):
        """LLM-only wine with rating: confidence capped at 0.75."""
        llm_wine = FastPipelineWine(
            wine_name="Unknown Wine With Rating",
            confidence=0.95,
            estimated_rating=4.0,
            bbox={"x": 0, "y": 0, "width": 0.1, "height": 0.3},
        )

        results = pipeline._match_against_db([llm_wine])

        assert len(results) == 1
        assert results[0].source == WineSource.LLM
        assert results[0].confidence <= 0.75

    def test_confidence_capping_without_rating(self, pipeline):
        """LLM-only wine without rating: confidence capped at 0.65."""
        llm_wine = FastPipelineWine(
            wine_name="Unknown Wine No Rating",
            confidence=0.95,
            estimated_rating=None,
            bbox={"x": 0, "y": 0, "width": 0.1, "height": 0.3},
        )

        results = pipeline._match_against_db([llm_wine])

        assert len(results) == 1
        assert results[0].source == WineSource.LLM
        assert results[0].confidence <= 0.65
        assert results[0].rating is None

    def test_synthetic_bottle_text_has_correct_bbox(self, pipeline):
        """BottleText created from LLM result has the LLM-provided bbox."""
        llm_wine = FastPipelineWine(
            wine_name="Test Wine",
            confidence=0.8,
            estimated_rating=3.9,
            bbox={"x": 0.25, "y": 0.30, "width": 0.12, "height": 0.45},
        )

        results = pipeline._match_against_db([llm_wine])

        assert len(results) == 1
        bt = results[0].bottle_text
        assert bt.bottle.bbox.x == 0.25
        assert bt.bottle.bbox.y == 0.30
        assert bt.bottle.bbox.width == 0.12
        assert bt.bottle.bbox.height == 0.45


# === Test Integration (Full Scan Flow) ===


class TestFastPipelineIntegration:
    """Test full scan flow with mocked LLM calls."""

    def _make_mock_response(self, wines_json: list[dict]) -> MagicMock:
        """Create a mock litellm response."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(wines_json)
        return mock_response

    @pytest.mark.asyncio
    async def test_full_scan_flow(self):
        """Mock litellm.acompletion, verify end-to-end scan."""
        wines_json = [
            {
                "wine_name": "Opus One",
                "confidence": 0.9,
                "estimated_rating": 4.6,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.4},
                "wine_type": "Red",
                "brand": "Opus One Winery",
                "region": "Napa Valley",
                "varietal": "Bordeaux Blend",
            },
            {
                "wine_name": "Caymus Cabernet Sauvignon",
                "confidence": 0.85,
                "estimated_rating": 4.3,
                "bbox": {"x": 0.3, "y": 0.1, "width": 0.12, "height": 0.45},
                "wine_type": "Red",
            },
        ]

        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(
            return_value=self._make_mock_response(wines_json)
        )

        pipeline = FastPipeline(
            wine_matcher=WineMatcher(),
            use_llm_cache=False,
        )

        with patch("app.services.fast_pipeline._get_litellm", return_value=mock_litellm), \
             patch("app.services.fast_pipeline._compress_image_for_vision", return_value=b"fake_jpeg"):
            result = await pipeline.scan(b"fake_image_bytes")

        assert isinstance(result, FastPipelineResult)
        assert len(result.recognized_wines) == 2
        assert len(result.raw_llm_wines) == 2

        # Both should be DB-matched since they exist in the database
        wine_names = {w.wine_name for w in result.recognized_wines}
        assert "Opus One" in wine_names

        # Timing data should be populated
        assert "llm_call_ms" in result.timings
        assert "db_lookup_ms" in result.timings
        assert "total_ms" in result.timings

        # litellm.acompletion should have been called exactly once
        mock_litellm.acompletion.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty(self):
        """Empty LLM response returns empty result (no crash)."""
        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(
            return_value=self._make_mock_response([])
        )

        pipeline = FastPipeline(
            wine_matcher=WineMatcher(),
            use_llm_cache=False,
        )

        with patch("app.services.fast_pipeline._get_litellm", return_value=mock_litellm), \
             patch("app.services.fast_pipeline._compress_image_for_vision", return_value=b"fake_jpeg"):
            result = await pipeline.scan(b"fake_image_bytes")

        assert isinstance(result, FastPipelineResult)
        assert len(result.recognized_wines) == 0
        assert len(result.raw_llm_wines) == 0

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty(self):
        """Exception during LLM call returns empty results (no crash)."""
        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(
            side_effect=Exception("API rate limit exceeded")
        )

        pipeline = FastPipeline(
            wine_matcher=WineMatcher(),
            use_llm_cache=False,
        )

        with patch("app.services.fast_pipeline._get_litellm", return_value=mock_litellm), \
             patch("app.services.fast_pipeline._compress_image_for_vision", return_value=b"fake_jpeg"):
            result = await pipeline.scan(b"fake_image_bytes")

        assert isinstance(result, FastPipelineResult)
        assert len(result.recognized_wines) == 0

    @pytest.mark.asyncio
    async def test_litellm_unavailable_returns_empty(self):
        """If litellm is not installed, returns empty results."""
        pipeline = FastPipeline(
            wine_matcher=WineMatcher(),
            use_llm_cache=False,
        )

        with patch("app.services.fast_pipeline._get_litellm", return_value=None):
            result = await pipeline.scan(b"fake_image_bytes")

        assert isinstance(result, FastPipelineResult)
        assert len(result.recognized_wines) == 0

    @pytest.mark.asyncio
    async def test_mixed_db_and_llm_wines(self):
        """Some wines match DB, others are LLM-only."""
        wines_json = [
            {
                "wine_name": "Opus One",
                "confidence": 0.9,
                "estimated_rating": 4.5,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.4},
            },
            {
                "wine_name": "Some Totally Unknown Wine ABC",
                "confidence": 0.7,
                "estimated_rating": 3.8,
                "bbox": {"x": 0.4, "y": 0.1, "width": 0.1, "height": 0.4},
            },
        ]

        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(
            return_value=self._make_mock_response(wines_json)
        )

        pipeline = FastPipeline(
            wine_matcher=WineMatcher(),
            use_llm_cache=False,
        )

        with patch("app.services.fast_pipeline._get_litellm", return_value=mock_litellm), \
             patch("app.services.fast_pipeline._compress_image_for_vision", return_value=b"fake_jpeg"):
            result = await pipeline.scan(b"fake_image_bytes")

        assert len(result.recognized_wines) == 2

        # Find DB-matched and LLM-only wines
        db_wines = [w for w in result.recognized_wines if w.source == WineSource.DATABASE]
        llm_wines = [w for w in result.recognized_wines if w.source == WineSource.LLM]

        assert len(db_wines) == 1
        assert db_wines[0].wine_name == "Opus One"
        assert db_wines[0].rating_source == RatingSource.DATABASE

        assert len(llm_wines) == 1
        assert llm_wines[0].wine_name == "Some Totally Unknown Wine ABC"
        assert llm_wines[0].rating == 3.8
        assert llm_wines[0].confidence <= 0.75  # Capped
