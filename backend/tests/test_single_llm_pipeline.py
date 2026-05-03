"""
Tests for the single-LLM wine recognition pipeline.

Replaces the multi-stage Vision-API + Gemini-Flash + spatial-merge pipeline
with one multimodal LLM call (Sonnet 4.6 by default, swappable via
SINGLE_LLM_MODEL env var). Vintage is a first-class returned field.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import Config
from app.services.single_llm_pipeline import (
    SingleLLMPipeline,
    SingleLLMWine,
    SingleLLMResult,
    _parse_llm_response,
)
from app.services.recognition_pipeline import RecognizedWine
from app.services.wine_matcher import WineMatcher
from app.services.llm_rating_cache import get_llm_rating_cache
from app.models.enums import RatingSource, WineSource


# === Test Response Parsing ===


class TestSingleLLMResponseParsing:
    """_parse_llm_response() turns LLM JSON into SingleLLMWine objects."""

    def test_parse_valid_response(self):
        response = json.dumps([
            {
                "wine_name": "Caymus Cabernet Sauvignon",
                "vintage": "2021",
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
                "vintage": None,
                "confidence": 0.85,
                "estimated_rating": 4.6,
                "bbox": {"x": 0.3, "y": 0.1, "width": 0.12, "height": 0.5},
            },
        ])

        results = _parse_llm_response(response)

        assert len(results) == 2
        assert results[0].wine_name == "Caymus Cabernet Sauvignon"
        assert results[0].vintage == "2021"
        assert results[0].varietal == "Cabernet Sauvignon"

        assert results[1].wine_name == "Opus One"
        assert results[1].vintage is None
        assert results[1].estimated_rating == 4.6

    def test_parse_response_with_markdown(self):
        response = '```json\n[{"wine_name": "Caymus", "vintage": "2020", "confidence": 0.8, "estimated_rating": 4.0, "bbox": {"x": 0, "y": 0, "width": 0.1, "height": 0.3}}]\n```'
        results = _parse_llm_response(response)
        assert len(results) == 1
        assert results[0].wine_name == "Caymus"
        assert results[0].vintage == "2020"

    def test_parse_response_with_null_wines(self):
        """Entries with null wine_name are filtered out (no overlay possible)."""
        response = json.dumps([
            {
                "wine_name": "Caymus",
                "vintage": "2021",
                "confidence": 0.8,
                "estimated_rating": 4.0,
                "bbox": {"x": 0, "y": 0, "width": 0.1, "height": 0.3},
            },
            {
                "wine_name": None,
                "vintage": None,
                "confidence": 0.3,
                "estimated_rating": None,
                "bbox": {"x": 0.5, "y": 0.1, "width": 0.1, "height": 0.3},
            },
        ])

        results = _parse_llm_response(response)
        assert len(results) == 1
        assert results[0].wine_name == "Caymus"

    def test_parse_invalid_json(self):
        results = _parse_llm_response("this is not json at all")
        assert results == []

    def test_parse_empty_array(self):
        assert _parse_llm_response("[]") == []

    def test_parse_non_array_json(self):
        assert _parse_llm_response('{"wine_name": "test"}') == []

    def test_parse_clamps_rating(self):
        response = json.dumps([
            {"wine_name": "A", "estimated_rating": 7.5, "confidence": 0.8,
             "bbox": {"x": 0, "y": 0, "width": 0.1, "height": 0.3}},
            {"wine_name": "B", "estimated_rating": -1.0, "confidence": 0.8,
             "bbox": {"x": 0.5, "y": 0, "width": 0.1, "height": 0.3}},
        ])
        results = _parse_llm_response(response)
        assert results[0].estimated_rating == 5.0
        assert results[1].estimated_rating == 1.0

    def test_parse_missing_bbox(self):
        response = json.dumps([{"wine_name": "X", "confidence": 0.7, "estimated_rating": 3.8}])
        results = _parse_llm_response(response)
        assert len(results) == 1
        assert results[0].bbox == {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}

    def test_parse_default_confidence(self):
        response = json.dumps([{"wine_name": "X", "estimated_rating": 3.8,
                                "bbox": {"x": 0, "y": 0, "width": 0.1, "height": 0.3}}])
        results = _parse_llm_response(response)
        assert results[0].confidence == 0.5

    def test_parse_rejects_nonnumeric_vintage(self):
        """Model occasionally returns "NV" or similar — coerce to None."""
        response = json.dumps([
            {"wine_name": "Champagne X", "vintage": "NV", "confidence": 0.8,
             "estimated_rating": 4.0,
             "bbox": {"x": 0, "y": 0, "width": 0.1, "height": 0.3}},
        ])
        results = _parse_llm_response(response)
        assert len(results) == 1
        assert results[0].vintage is None


# === Test DB Matching ===


class TestSingleLLMDBMatching:
    """_match_against_db cross-references LLM results with the wine DB."""

    @pytest.fixture
    def pipeline(self):
        return SingleLLMPipeline(
            wine_matcher=WineMatcher(),
            use_llm_cache=False,
        )

    def test_db_match_uses_authoritative_rating(self, pipeline):
        llm_wine = SingleLLMWine(
            wine_name="Opus One",
            confidence=0.9,
            estimated_rating=4.5,
            bbox={"x": 0.1, "y": 0.2, "width": 0.1, "height": 0.4},
            vintage="2019",
        )

        results = pipeline._match_against_db([llm_wine])

        assert len(results) == 1
        assert results[0].source == WineSource.DATABASE
        assert results[0].rating_source == RatingSource.DATABASE
        assert results[0].rating is not None
        assert results[0].vintage == "2019"  # Vintage flows through DB-matched wines

    def test_no_db_match_uses_llm_rating(self, pipeline):
        llm_wine = SingleLLMWine(
            wine_name="Totally Unknown Boutique Wine XYZ",
            confidence=0.85,
            estimated_rating=4.1,
            bbox={"x": 0.1, "y": 0.2, "width": 0.1, "height": 0.4},
            vintage="2022",
        )

        results = pipeline._match_against_db([llm_wine])

        assert len(results) == 1
        assert results[0].source == WineSource.LLM
        assert results[0].rating_source == RatingSource.LLM_ESTIMATED
        assert results[0].rating == 4.1
        assert results[0].vintage == "2022"

    def test_confidence_capping_with_rating(self, pipeline):
        llm_wine = SingleLLMWine(
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
        llm_wine = SingleLLMWine(
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
        llm_wine = SingleLLMWine(
            wine_name="Test Wine",
            confidence=0.8,
            estimated_rating=3.9,
            bbox={"x": 0.25, "y": 0.30, "width": 0.12, "height": 0.45},
        )
        results = pipeline._match_against_db([llm_wine])
        bt = results[0].bottle_text
        assert bt.bottle.bbox.x == 0.25
        assert bt.bottle.bbox.y == 0.30
        assert bt.bottle.bbox.width == 0.12
        assert bt.bottle.bbox.height == 0.45


# === Test Model Selection ===


class TestSingleLLMModelSelection:
    """The pipeline uses the configured model and is swappable."""

    def test_default_model_from_config(self, monkeypatch):
        # Strip SINGLE_LLM_MODEL so the test asserts the in-code default,
        # not whatever the developer has set in .env.
        monkeypatch.delenv("SINGLE_LLM_MODEL", raising=False)
        pipeline = SingleLLMPipeline(wine_matcher=WineMatcher(), use_llm_cache=False)
        # Default points at Sonnet 4.6 (strong 2D bbox quality on dense shelves).
        # Haiku 4.5 was tried but degenerates to 1D-lane output — see CLAUDE.md
        # "Known limitations" and docs/SINGLE_LLM_PIVOT_PLAN.md "Notes — Phase F".
        assert pipeline._select_model() == "anthropic/claude-sonnet-4-6"
        assert Config.single_llm_model() == "anthropic/claude-sonnet-4-6"

    def test_explicit_model_override(self):
        pipeline = SingleLLMPipeline(
            wine_matcher=WineMatcher(),
            use_llm_cache=False,
            model="gemini/gemini-2.5-pro",
        )
        assert pipeline._select_model() == "gemini/gemini-2.5-pro"


# === Test Integration (Full Scan Flow) ===


class TestSingleLLMIntegration:
    """Full scan flow with mocked LLM calls."""

    def _make_mock_response(self, wines_json: list[dict]) -> MagicMock:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(wines_json)
        return mock_response

    @pytest.mark.asyncio
    async def test_full_scan_flow_with_vintage(self):
        """End-to-end: mock LLM, verify vintage flows through to RecognizedWine."""
        wines_json = [
            {
                "wine_name": "Opus One",
                "vintage": "2019",
                "confidence": 0.9,
                "estimated_rating": 4.6,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.4},
            },
            {
                "wine_name": "Caymus Cabernet Sauvignon",
                "vintage": "2021",
                "confidence": 0.85,
                "estimated_rating": 4.3,
                "bbox": {"x": 0.3, "y": 0.1, "width": 0.12, "height": 0.45},
            },
        ]

        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(
            return_value=self._make_mock_response(wines_json)
        )

        pipeline = SingleLLMPipeline(
            wine_matcher=WineMatcher(),
            use_llm_cache=False,
        )

        with patch("app.services.single_llm_pipeline._get_litellm", return_value=mock_litellm), \
             patch("app.services.single_llm_pipeline._compress_image_for_vision", return_value=b"fake_jpeg"):
            result = await pipeline.scan(b"fake_image_bytes")

        assert isinstance(result, SingleLLMResult)
        assert len(result.recognized_wines) == 2
        assert len(result.raw_llm_wines) == 2

        vintages = {w.vintage for w in result.recognized_wines}
        assert "2019" in vintages
        assert "2021" in vintages

        assert "llm_call_ms" in result.timings
        assert result.timings["model"] == Config.single_llm_model()

        mock_litellm.acompletion.assert_called_once()
        call_kwargs = mock_litellm.acompletion.call_args.kwargs
        assert call_kwargs["model"] == Config.single_llm_model()

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty(self):
        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(
            return_value=self._make_mock_response([])
        )

        pipeline = SingleLLMPipeline(wine_matcher=WineMatcher(), use_llm_cache=False)

        with patch("app.services.single_llm_pipeline._get_litellm", return_value=mock_litellm), \
             patch("app.services.single_llm_pipeline._compress_image_for_vision", return_value=b"fake_jpeg"):
            result = await pipeline.scan(b"fake_image_bytes")

        assert isinstance(result, SingleLLMResult)
        assert len(result.recognized_wines) == 0

    @pytest.mark.asyncio
    async def test_llm_failure_propagates(self):
        """Exception during LLM call propagates (no silent fallback)."""
        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(
            side_effect=RuntimeError("API rate limit exceeded")
        )

        pipeline = SingleLLMPipeline(wine_matcher=WineMatcher(), use_llm_cache=False)

        with patch("app.services.single_llm_pipeline._get_litellm", return_value=mock_litellm), \
             patch("app.services.single_llm_pipeline._compress_image_for_vision", return_value=b"fake_jpeg"):
            with pytest.raises(RuntimeError, match="rate limit"):
                await pipeline.scan(b"fake_image_bytes")

    @pytest.mark.asyncio
    async def test_litellm_unavailable_raises(self):
        """If litellm is not installed, the pipeline raises rather than silently failing."""
        pipeline = SingleLLMPipeline(wine_matcher=WineMatcher(), use_llm_cache=False)

        with patch("app.services.single_llm_pipeline._get_litellm", return_value=None):
            with pytest.raises(RuntimeError, match="litellm"):
                await pipeline.scan(b"fake_image_bytes")

    @pytest.mark.asyncio
    async def test_mixed_db_and_llm_wines(self):
        wines_json = [
            {
                "wine_name": "Opus One",
                "vintage": "2018",
                "confidence": 0.9,
                "estimated_rating": 4.5,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.4},
            },
            {
                "wine_name": "Some Totally Unknown Wine ABC",
                "vintage": "2023",
                "confidence": 0.7,
                "estimated_rating": 3.8,
                "bbox": {"x": 0.4, "y": 0.1, "width": 0.1, "height": 0.4},
            },
        ]

        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(
            return_value=self._make_mock_response(wines_json)
        )

        pipeline = SingleLLMPipeline(wine_matcher=WineMatcher(), use_llm_cache=False)

        with patch("app.services.single_llm_pipeline._get_litellm", return_value=mock_litellm), \
             patch("app.services.single_llm_pipeline._compress_image_for_vision", return_value=b"fake_jpeg"):
            result = await pipeline.scan(b"fake_image_bytes")

        db_wines = [w for w in result.recognized_wines if w.source == WineSource.DATABASE]
        llm_wines = [w for w in result.recognized_wines if w.source == WineSource.LLM]
        assert len(db_wines) == 1
        assert db_wines[0].wine_name == "Opus One"
        assert db_wines[0].vintage == "2018"
        assert len(llm_wines) == 1
        assert llm_wines[0].wine_name == "Some Totally Unknown Wine ABC"
        assert llm_wines[0].vintage == "2023"
        assert llm_wines[0].confidence <= 0.75


# === Test Cache Round-Trip ===


class TestSingleLLMCacheVintage:
    """Vintage round-trips through the LLM rating cache."""

    @pytest.mark.asyncio
    async def test_vintage_persists_to_cache(self, tmp_path):
        """Cache.set with vintage is callable and persists the field."""
        cache = get_llm_rating_cache()

        unique_name = "Test Vintage Cache Wine ZZZ"
        cache.set(
            wine_name=unique_name,
            estimated_rating=4.0,
            confidence=0.8,
            llm_provider="anthropic/claude-sonnet-4-6",
            wine_type="Red",
            vintage="2017",
        )

        cached = cache.get(unique_name, increment_hit=False)
        assert cached is not None
        assert cached.vintage == "2017"
        cache.delete(unique_name)
