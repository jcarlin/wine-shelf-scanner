"""
Tests for the tiered recognition pipeline.

Tests the full recognition flow:
1. Enhanced fuzzy match (confidence >= 0.7) -> no LLM call
2. Fuzzy match fails (confidence < 0.7) -> LLM fallback triggered
3. LLM normalizes text -> re-match succeeds
4. Confidence filtering (>= 0.45 -> results, < 0.45 -> fallback)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.recognition_pipeline import RecognitionPipeline, RecognizedWine
from app.services.wine_matcher import WineMatcher, WineMatch
from app.services.llm_normalizer import (
    NormalizerProtocol,
    NormalizationResult,
    MockNormalizer,
)
from app.services.ocr_processor import BottleText
from app.services.vision import DetectedObject, BoundingBox


def create_bottle_text(
    normalized_name: str,
    combined_text: str = None,
    confidence: float = 0.95,
) -> BottleText:
    """Helper to create BottleText for testing."""
    return BottleText(
        bottle=DetectedObject(
            name="Bottle",
            confidence=confidence,
            bbox=BoundingBox(x=0.1, y=0.1, width=0.1, height=0.3),
        ),
        text_fragments=[normalized_name],
        combined_text=combined_text or normalized_name,
        normalized_name=normalized_name,
    )


class TestRecognitionPipelineThresholds:
    """Test recognition pipeline confidence thresholds."""

    @pytest.fixture
    def pipeline(self):
        """Create pipeline with mock normalizer."""
        return RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=MockNormalizer(),
            use_llm=True,
        )

    @pytest.mark.asyncio
    async def test_high_confidence_db_match_no_llm(self, pipeline):
        """Test that high-confidence DB match (>= 0.7) doesn't trigger LLM."""
        # "Opus One" is in the database and should match with high confidence
        bottle_text = create_bottle_text("Opus One")

        results = await pipeline.recognize([bottle_text])

        assert len(results) == 1
        assert results[0].wine_name == "Opus One"
        assert results[0].rating == 4.8
        assert results[0].confidence >= 0.7
        assert results[0].source == "database"
        assert results[0].identified is True

    @pytest.mark.asyncio
    async def test_exact_match_returns_confidence_1(self, pipeline):
        """Test exact match returns confidence 1.0."""
        bottle_text = create_bottle_text("Opus One")

        results = await pipeline.recognize([bottle_text])

        assert len(results) == 1
        # Confidence should be min of bottle confidence (0.95) and match confidence (1.0)
        assert results[0].confidence == 0.95

    @pytest.mark.asyncio
    async def test_fuzzy_match_high_confidence(self, pipeline):
        """Test fuzzy match with high enough confidence to bypass LLM."""
        # "Caymus" is an alias for "Caymus Cabernet Sauvignon"
        bottle_text = create_bottle_text("Caymus")

        results = await pipeline.recognize([bottle_text])

        assert len(results) == 1
        assert results[0].wine_name == "Caymus Cabernet Sauvignon"
        assert results[0].rating == 4.5

    @pytest.mark.asyncio
    async def test_empty_text_returns_none(self, pipeline):
        """Test that empty/short text returns no results."""
        bottle_text = create_bottle_text("")

        results = await pipeline.recognize([bottle_text])

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_short_text_returns_none(self, pipeline):
        """Test that very short text (< 3 chars) returns no results."""
        bottle_text = create_bottle_text("AB")

        results = await pipeline.recognize([bottle_text])

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_multiple_bottles(self, pipeline):
        """Test recognition of multiple bottles."""
        bottle_texts = [
            create_bottle_text("Opus One"),
            create_bottle_text("Caymus"),
            create_bottle_text("Silver Oak"),
        ]

        results = await pipeline.recognize(bottle_texts)

        assert len(results) == 3
        wine_names = {r.wine_name for r in results}
        assert "Opus One" in wine_names
        assert "Caymus Cabernet Sauvignon" in wine_names
        assert "Silver Oak Alexander Valley" in wine_names


class TestRecognitionPipelineLLMFallback:
    """Test LLM fallback behavior when fuzzy match fails."""

    @pytest.mark.asyncio
    async def test_llm_fallback_triggered_for_low_confidence(self):
        """Test that LLM fallback is triggered for low-confidence matches."""
        # Create a custom normalizer that tracks calls
        call_count = 0

        class TrackingNormalizer:
            async def normalize(self, ocr_text, context=None):
                nonlocal call_count
                call_count += 1
                return NormalizationResult(
                    wine_name="Opus One",
                    confidence=0.85,
                    is_wine=True,
                    reasoning="Test",
                )

        pipeline = RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=TrackingNormalizer(),
            use_llm=True,
        )

        # Use garbled text that won't match well in DB
        # (very different from any wine name to avoid fuzzy match)
        bottle_text = create_bottle_text("XYZZY Winery Reserve Blend")

        results = await pipeline.recognize([bottle_text])

        # LLM should have been called since fuzzy match won't have high confidence
        assert call_count == 1
        assert len(results) == 1
        # LLM normalized to "Opus One" which matches DB
        assert results[0].wine_name == "Opus One"
        assert results[0].source == "database"

    @pytest.mark.asyncio
    async def test_llm_disabled_skips_fallback(self):
        """Test that LLM fallback is skipped when use_llm=False."""
        call_count = 0

        class TrackingNormalizer:
            async def normalize(self, ocr_text, context=None):
                nonlocal call_count
                call_count += 1
                return NormalizationResult(
                    wine_name="Opus One",
                    confidence=0.85,
                    is_wine=True,
                    reasoning="Test",
                )

        pipeline = RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=TrackingNormalizer(),
            use_llm=False,  # LLM disabled
        )

        # Use garbled text
        bottle_text = create_bottle_text("Opsu Oen")

        results = await pipeline.recognize([bottle_text])

        # LLM should NOT have been called
        assert call_count == 0

    @pytest.mark.asyncio
    async def test_llm_identifies_wine_not_in_db(self):
        """Test LLM can identify wine not in database."""

        class UnknownWineNormalizer:
            async def normalize(self, ocr_text, context=None):
                return NormalizationResult(
                    wine_name="Unknown Boutique Wine",
                    confidence=0.75,
                    is_wine=True,
                    reasoning="Identified as wine from label patterns",
                )

        pipeline = RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=UnknownWineNormalizer(),
            use_llm=True,
        )

        bottle_text = create_bottle_text("Boutique Wine Estate Reserve")

        results = await pipeline.recognize([bottle_text])

        assert len(results) == 1
        assert results[0].wine_name == "Unknown Boutique Wine"
        assert results[0].rating is None  # Not in DB
        assert results[0].source == "llm"
        assert results[0].identified is True

    @pytest.mark.asyncio
    async def test_llm_rejects_non_wine(self):
        """Test LLM correctly rejects non-wine text."""

        class RejectingNormalizer:
            async def normalize(self, ocr_text, context=None):
                return NormalizationResult(
                    wine_name=None,
                    confidence=0.0,
                    is_wine=False,
                    reasoning="This appears to be a price tag",
                )

        pipeline = RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=RejectingNormalizer(),
            use_llm=True,
        )

        bottle_text = create_bottle_text("$24.99 SALE")

        results = await pipeline.recognize([bottle_text])

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_llm_low_confidence_not_used_as_source(self):
        """Test LLM results with confidence < 0.6 don't become the source."""

        class LowConfidenceNormalizer:
            async def normalize(self, ocr_text, context=None):
                return NormalizationResult(
                    wine_name="LLM Identified Wine",
                    confidence=0.4,  # Below 0.6 threshold
                    is_wine=True,
                    reasoning="Very uncertain",
                )

        pipeline = RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=LowConfidenceNormalizer(),
            use_llm=True,
        )

        # Use text that triggers LLM but LLM result is low confidence
        bottle_text = create_bottle_text("Unknown Text Here")

        results = await pipeline.recognize([bottle_text])

        # If there's a result, it should NOT be from LLM with the low-confidence name
        for result in results:
            assert result.wine_name != "LLM Identified Wine"
            # If we got a result, it should be from database fallback
            if result.source == "llm":
                assert result.confidence >= 0.6


class TestRecognitionPipelineConfidenceFiltering:
    """Test confidence filtering for main results vs fallback."""

    @pytest.fixture
    def pipeline(self):
        return RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=MockNormalizer(),
            use_llm=False,
        )

    @pytest.mark.asyncio
    async def test_confidence_above_fallback_threshold(self, pipeline):
        """Test matches above 0.45 are included in results."""
        # "Opus One" should match with very high confidence
        bottle_text = create_bottle_text("Opus One")

        results = await pipeline.recognize([bottle_text])

        assert len(results) == 1
        assert results[0].confidence >= RecognitionPipeline.FALLBACK_THRESHOLD

    @pytest.mark.asyncio
    async def test_minimum_confidence_preserved(self, pipeline):
        """Test that confidence is the min of bottle and match confidence."""
        # Create bottle with low detection confidence
        bottle_text = create_bottle_text("Opus One", confidence=0.5)

        results = await pipeline.recognize([bottle_text])

        assert len(results) == 1
        # Should be limited by bottle confidence, not match confidence
        assert results[0].confidence == 0.5


class TestRecognitionPipelineRecognizedWine:
    """Test RecognizedWine dataclass attributes."""

    @pytest.fixture
    def pipeline(self):
        return RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=MockNormalizer(),
            use_llm=False,
        )

    @pytest.mark.asyncio
    async def test_recognized_wine_has_all_fields(self, pipeline):
        """Test RecognizedWine contains all required fields."""
        bottle_text = create_bottle_text("Opus One")

        results = await pipeline.recognize([bottle_text])

        assert len(results) == 1
        wine = results[0]

        # Check all fields exist and have correct types
        assert isinstance(wine.wine_name, str)
        assert isinstance(wine.rating, float) or wine.rating is None
        assert isinstance(wine.confidence, float)
        assert wine.source in ("database", "llm")
        assert isinstance(wine.identified, bool)
        assert isinstance(wine.bottle_text, BottleText)

    @pytest.mark.asyncio
    async def test_recognized_wine_preserves_bottle_text(self, pipeline):
        """Test RecognizedWine preserves original BottleText."""
        bottle_text = create_bottle_text(
            "Opus One",
            combined_text="OPUS ONE Napa Valley 2019",
        )

        results = await pipeline.recognize([bottle_text])

        assert len(results) == 1
        assert results[0].bottle_text is bottle_text
        assert results[0].bottle_text.combined_text == "OPUS ONE Napa Valley 2019"


class TestRecognitionPipelineIntegration:
    """Integration tests for the full pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_mock_vision_data(self):
        """Test pipeline with data similar to MockVisionService output."""
        pipeline = RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=MockNormalizer(),
            use_llm=True,
        )

        # Simulate bottle texts from vision service
        bottle_texts = [
            create_bottle_text("Caymus Cabernet Sauvignon", confidence=0.95),
            create_bottle_text("Opus One Napa Valley", confidence=0.93),
            create_bottle_text("Silver Oak", confidence=0.91),
            create_bottle_text("Jordan Cabernet", confidence=0.89),
        ]

        results = await pipeline.recognize(bottle_texts)

        assert len(results) == 4

        # Verify all are identified
        for result in results:
            assert result.identified is True
            assert result.source == "database"
            assert result.rating is not None
            assert result.confidence >= 0.45

    @pytest.mark.asyncio
    async def test_mixed_confidence_results(self):
        """Test pipeline with mix of high and low confidence matches."""
        pipeline = RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=MockNormalizer(),
            use_llm=False,
        )

        bottle_texts = [
            create_bottle_text("Opus One", confidence=0.95),  # High conf, matches DB
            create_bottle_text("XYZABC Gibberish", confidence=0.80),  # No match possible
            create_bottle_text("Caymus", confidence=0.70),  # Medium conf, matches DB
        ]

        results = await pipeline.recognize(bottle_texts)

        # Should have 2 results (Opus One and Caymus)
        # The gibberish text won't match anything
        assert len(results) == 2
        wine_names = {r.wine_name for r in results}
        assert "Opus One" in wine_names
        assert "Caymus Cabernet Sauvignon" in wine_names
