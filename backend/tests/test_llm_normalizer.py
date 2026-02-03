"""
Tests for the LLM normalizer service.

Tests:
- MockNormalizer behavior for predictable testing
- NormalizerProtocol interface compliance
- Normalization output format
- Error handling
- LiteLLMNormalizer response parsing and fallback behavior
"""

import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock

from app.services.llm_normalizer import (
    NormalizerProtocol,
    NormalizationResult,
    BatchValidationItem,
    BatchValidationResult,
    LiteLLMNormalizer,
    LLMNormalizerBase,
    MockNormalizer,
    get_normalizer,
    LITELLM_AVAILABLE,
)


class TestNormalizationResult:
    """Test NormalizationResult dataclass."""

    def test_result_has_all_fields(self):
        """Test NormalizationResult has all required fields."""
        result = NormalizationResult(
            wine_name="Test Wine",
            confidence=0.85,
            is_wine=True,
            reasoning="Test reasoning",
        )

        assert result.wine_name == "Test Wine"
        assert result.confidence == 0.85
        assert result.is_wine is True
        assert result.reasoning == "Test reasoning"

    def test_result_allows_none_wine_name(self):
        """Test NormalizationResult allows None wine_name."""
        result = NormalizationResult(
            wine_name=None,
            confidence=0.0,
            is_wine=False,
            reasoning="Not a wine",
        )

        assert result.wine_name is None
        assert result.is_wine is False


class TestMockNormalizer:
    """Test MockNormalizer for testing without API calls."""

    @pytest.fixture
    def normalizer(self):
        return MockNormalizer()

    @pytest.mark.asyncio
    async def test_identifies_wine_keywords(self, normalizer):
        """Test MockNormalizer identifies text with wine keywords."""
        result = await normalizer.normalize("Caymus Cabernet Sauvignon Napa Valley")

        assert result.is_wine is True
        assert result.wine_name == "Caymus Cabernet Sauvignon Napa Valley"
        assert result.confidence == 0.75
        assert "wine keywords" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_identifies_varietal_keywords(self, normalizer):
        """Test MockNormalizer identifies varietal names."""
        varietals = [
            "cabernet",
            "merlot",
            "pinot noir",
            "chardonnay",
            "sauvignon blanc",
            "riesling",
            "syrah",
            "zinfandel",
            "malbec",
        ]

        for varietal in varietals:
            result = await normalizer.normalize(f"Test {varietal}")
            assert result.is_wine is True, f"Should identify {varietal} as wine"

    @pytest.mark.asyncio
    async def test_identifies_region_keywords(self, normalizer):
        """Test MockNormalizer identifies wine region names."""
        regions = ["napa", "sonoma", "burgundy", "bordeaux"]

        for region in regions:
            result = await normalizer.normalize(f"Estate {region} Reserve")
            assert result.is_wine is True, f"Should identify {region} as wine"

    @pytest.mark.asyncio
    async def test_identifies_winery_keywords(self, normalizer):
        """Test MockNormalizer identifies winery-style terms."""
        winery_terms = ["chateau", "domaine", "vineyard", "estate"]

        for term in winery_terms:
            result = await normalizer.normalize(f"{term} Test")
            assert result.is_wine is True, f"Should identify {term} as wine"

    @pytest.mark.asyncio
    async def test_rejects_non_wine_keywords(self, normalizer):
        """Test MockNormalizer rejects text with non-wine keywords."""
        non_wine_texts = [
            "Contains sulfites warning",
            "Government warning pregnant",
            "$24.99 price tag",
            "shelf tag sale",
        ]

        for text in non_wine_texts:
            result = await normalizer.normalize(text)
            assert result.is_wine is False, f"Should reject: {text}"
            assert result.wine_name is None

    @pytest.mark.asyncio
    async def test_rejects_text_without_wine_or_non_wine_keywords(self, normalizer):
        """Test MockNormalizer rejects ambiguous text."""
        result = await normalizer.normalize("Random Text Here")

        assert result.is_wine is False
        assert result.wine_name is None
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_normalizes_wine_name_to_title_case(self, normalizer):
        """Test MockNormalizer title-cases the wine name."""
        result = await normalizer.normalize("CAYMUS CABERNET")

        assert result.wine_name == "Caymus Cabernet"

    @pytest.mark.asyncio
    async def test_context_is_ignored(self, normalizer):
        """Test MockNormalizer ignores context parameter."""
        result = await normalizer.normalize(
            "Opus One Cabernet",
            context={"bottle_confidence": 0.95, "text_fragments": ["OPUS", "ONE"]},
        )

        assert result.is_wine is True
        assert result.wine_name == "Opus One Cabernet"


class TestLLMNormalizerBaseResponseParsing:
    """Test LLMNormalizerBase response parsing logic."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON response."""
        normalizer = LiteLLMNormalizer(models=[])

        response = '{"wine_name": "Opus One", "confidence": 0.9, "is_wine": true, "reasoning": "Clear label"}'
        result = normalizer._parse_response(response)

        assert result.wine_name == "Opus One"
        assert result.confidence == 0.9
        assert result.is_wine is True
        assert result.reasoning == "Clear label"

    def test_parse_json_with_markdown_code_block(self):
        """Test parsing JSON wrapped in markdown code block."""
        normalizer = LiteLLMNormalizer(models=[])

        response = """```json
{"wine_name": "Caymus", "confidence": 0.85, "is_wine": true, "reasoning": "Recognized brand"}
```"""
        result = normalizer._parse_response(response)

        assert result.wine_name == "Caymus"
        assert result.confidence == 0.85

    def test_parse_json_with_plain_code_block(self):
        """Test parsing JSON wrapped in plain code block."""
        normalizer = LiteLLMNormalizer(models=[])

        response = """```
{"wine_name": "Silver Oak", "confidence": 0.8, "is_wine": true, "reasoning": "Test"}
```"""
        result = normalizer._parse_response(response)

        assert result.wine_name == "Silver Oak"

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns error result."""
        normalizer = LiteLLMNormalizer(models=[])

        response = "This is not valid JSON"
        result = normalizer._parse_response(response)

        assert result.wine_name is None
        assert result.confidence == 0.0
        assert result.is_wine is False
        assert "Parse error" in result.reasoning

    def test_parse_missing_fields_uses_defaults(self):
        """Test parsing JSON with missing fields uses defaults."""
        normalizer = LiteLLMNormalizer(models=[])

        response = '{"wine_name": "Test Wine"}'
        result = normalizer._parse_response(response)

        assert result.wine_name == "Test Wine"
        assert result.confidence == 0.5  # Default
        assert result.is_wine is False  # Default
        assert result.reasoning == ""  # Default

    def test_parse_null_wine_name(self):
        """Test parsing JSON with null wine_name."""
        normalizer = LiteLLMNormalizer(models=[])

        response = '{"wine_name": null, "confidence": 0.0, "is_wine": false, "reasoning": "Not a wine"}'
        result = normalizer._parse_response(response)

        assert result.wine_name is None
        assert result.is_wine is False


class TestLiteLLMNormalizerEmptyInput:
    """Test LiteLLMNormalizer handling of empty/short input."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_early(self):
        """Test empty text returns immediately without API call."""
        normalizer = LiteLLMNormalizer(models=["test-model"])

        result = await normalizer.normalize("")

        assert result.wine_name is None
        assert result.confidence == 0.0
        assert result.is_wine is False
        assert "too short" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_short_text_returns_early(self):
        """Test very short text (< 3 chars) returns immediately."""
        normalizer = LiteLLMNormalizer(models=["test-model"])

        result = await normalizer.normalize("AB")

        assert result.wine_name is None
        assert result.is_wine is False


class TestGetNormalizerFactory:
    """Test the get_normalizer factory function."""

    def test_returns_mock_when_use_mock_true(self):
        """Test factory returns MockNormalizer when use_mock=True."""
        normalizer = get_normalizer(use_mock=True)

        assert isinstance(normalizer, MockNormalizer)

    def test_returns_litellm_when_available(self):
        """Test factory returns LiteLLMNormalizer when LiteLLM is available."""
        with patch("app.services.llm_normalizer.LITELLM_AVAILABLE", True):
            normalizer = get_normalizer(use_mock=False)
            assert isinstance(normalizer, LiteLLMNormalizer)

    def test_returns_mock_when_litellm_not_available(self):
        """Test factory returns MockNormalizer when LiteLLM not installed."""
        with patch("app.services.llm_normalizer.LITELLM_AVAILABLE", False):
            normalizer = get_normalizer(use_mock=False)
            assert isinstance(normalizer, MockNormalizer)


class TestNormalizerProtocolCompliance:
    """Test that normalizers comply with NormalizerProtocol."""

    @pytest.mark.asyncio
    async def test_mock_normalizer_implements_protocol(self):
        """Test MockNormalizer implements NormalizerProtocol."""
        normalizer = MockNormalizer()

        # Should have normalize method with correct signature
        assert hasattr(normalizer, "normalize")

        # Should return NormalizationResult
        result = await normalizer.normalize("test", context=None)
        assert isinstance(result, NormalizationResult)

    @pytest.mark.asyncio
    async def test_litellm_normalizer_implements_protocol(self):
        """Test LiteLLMNormalizer implements NormalizerProtocol."""
        normalizer = LiteLLMNormalizer(models=[])

        # Should have normalize method
        assert hasattr(normalizer, "normalize")

        # Test with short input that returns early (no API call)
        result = await normalizer.normalize("AB", context=None)
        assert isinstance(result, NormalizationResult)


class TestMockNormalizerWineKeywords:
    """Test MockNormalizer wine keyword detection in detail."""

    @pytest.fixture
    def normalizer(self):
        return MockNormalizer()

    @pytest.mark.asyncio
    async def test_case_insensitive_keyword_matching(self, normalizer):
        """Test keyword matching is case insensitive."""
        texts = ["CABERNET", "Cabernet", "cabernet", "CaBeRnEt"]

        for text in texts:
            result = await normalizer.normalize(text)
            assert result.is_wine is True, f"Should match {text}"

    @pytest.mark.asyncio
    async def test_partial_keyword_in_word(self, normalizer):
        """Test keywords match when part of larger word."""
        # "cabernet" should match even in "CabernetSauvignon" (no space)
        result = await normalizer.normalize("CabernetSauvignon")

        assert result.is_wine is True

    @pytest.mark.asyncio
    async def test_non_wine_keywords_take_precedence(self, normalizer):
        """Test non-wine keywords reject even if wine keywords present."""
        # "cabernet" is wine keyword, but "warning" is non-wine
        result = await normalizer.normalize("Cabernet Sauvignon Government Warning")

        assert result.is_wine is False

    @pytest.mark.asyncio
    async def test_rose_with_accent(self, normalizer):
        """Test rose with accent is recognized."""
        result = await normalizer.normalize("Whispering Angel Rosé")

        assert result.is_wine is True

    @pytest.mark.asyncio
    async def test_rose_without_accent(self, normalizer):
        """Test rose without accent is recognized."""
        result = await normalizer.normalize("Summer Rose Wine")

        assert result.is_wine is True


class TestLiteLLMNormalizerConfiguration:
    """Test LiteLLMNormalizer model configuration."""

    def test_builds_model_list_from_env(self):
        """Test model list is built from environment config."""
        with patch.object(LiteLLMNormalizer, "_get_configured_models") as mock_config:
            mock_config.return_value = ["gemini/gemini-2.0-flash", "claude-3-haiku-20240307"]
            normalizer = LiteLLMNormalizer()

            assert len(normalizer.models) == 2
            assert "gemini" in normalizer.models[0]

    def test_accepts_custom_model_list(self):
        """Test custom model list overrides environment."""
        custom_models = ["gpt-4o-mini", "claude-3-haiku-20240307"]
        normalizer = LiteLLMNormalizer(models=custom_models)

        assert normalizer.models == custom_models

    def test_empty_models_when_no_keys_configured(self):
        """Test empty model list when no API keys configured."""
        with patch("app.config.Config.gemini_api_key", return_value=None), \
             patch("app.config.Config.anthropic_api_key", return_value=None), \
             patch("app.config.Config.openai_api_key", return_value=None), \
             patch("app.config.Config.llm_provider", return_value="gemini"):
            normalizer = LiteLLMNormalizer()
            assert normalizer.models == []


class TestLiteLLMNormalizerFallback:
    """Test LiteLLMNormalizer automatic fallback between providers."""

    @pytest.mark.asyncio
    async def test_fallback_to_heuristics_when_no_models(self):
        """When no models configured, should fall back to heuristics for validation."""
        normalizer = LiteLLMNormalizer(models=[])

        items = [
            BatchValidationItem(ocr_text="Caymus Cabernet", db_candidate="Caymus Cabernet Sauvignon", db_rating=4.5)
        ]
        results = await normalizer.validate_batch(items)

        assert len(results) == 1
        # Heuristic validation should still work
        assert isinstance(results[0], BatchValidationResult)

    @pytest.mark.asyncio
    async def test_litellm_not_available_uses_heuristics(self):
        """When LiteLLM not installed, should fall back to heuristics."""
        with patch("app.services.llm_normalizer.LITELLM_AVAILABLE", False):
            normalizer = LiteLLMNormalizer(models=["gemini/gemini-2.0-flash"])

            items = [
                BatchValidationItem(ocr_text="Silver Oak", db_candidate="Silver Oak Cabernet", db_rating=4.3)
            ]
            results = await normalizer.validate_batch(items)

            assert len(results) == 1
            assert isinstance(results[0], BatchValidationResult)

    @pytest.mark.asyncio
    @pytest.mark.skipif(not LITELLM_AVAILABLE, reason="LiteLLM not installed")
    async def test_api_error_falls_back_to_heuristics(self):
        """When all LLM providers fail, should fall back to heuristics."""
        with patch("litellm.acompletion", side_effect=Exception("All providers failed")):
            normalizer = LiteLLMNormalizer(models=["gemini/gemini-2.0-flash"])

            items = [
                BatchValidationItem(ocr_text="Opus One", db_candidate="Opus One Napa Valley", db_rating=4.8)
            ]
            results = await normalizer.validate_batch(items)

            assert len(results) == 1
            # Should get heuristic result, not raise exception
            assert isinstance(results[0], BatchValidationResult)

    @pytest.mark.asyncio
    @pytest.mark.skipif(not LITELLM_AVAILABLE, reason="LiteLLM not installed")
    async def test_normalize_api_error_returns_graceful_result(self):
        """When normalize fails, should return graceful error result."""
        with patch("litellm.acompletion", side_effect=Exception("API Error")):
            normalizer = LiteLLMNormalizer(models=["gemini/gemini-2.0-flash"])

            result = await normalizer.normalize("Caymus Cabernet Sauvignon")

            assert result.wine_name is None
            assert result.confidence == 0.0
            assert result.is_wine is False
            assert "LLM error" in result.reasoning

    @pytest.mark.asyncio
    @pytest.mark.skipif(not LITELLM_AVAILABLE, reason="LiteLLM not installed")
    async def test_validate_api_error_falls_back_to_heuristics(self):
        """When validate fails, should fall back to heuristic validation."""
        with patch("litellm.acompletion", side_effect=Exception("API Error")):
            normalizer = LiteLLMNormalizer(models=["gemini/gemini-2.0-flash"])

            result = await normalizer.validate(
                ocr_text="Caymus Cabernet",
                db_candidate="Caymus Cabernet Sauvignon",
                db_rating=4.5
            )

            # Should get heuristic result, not raise exception
            assert result.wine_name is not None
            assert result.confidence > 0


class TestLiteLLMNormalizerProtocolCompliance:
    """Test that LiteLLMNormalizer complies with NormalizerProtocol."""

    @pytest.mark.asyncio
    async def test_implements_normalize(self):
        """Test LiteLLMNormalizer implements normalize method."""
        normalizer = LiteLLMNormalizer(models=[])

        assert hasattr(normalizer, "normalize")

        # Test with short input that returns early (no API call)
        result = await normalizer.normalize("AB")
        assert isinstance(result, NormalizationResult)

    @pytest.mark.asyncio
    async def test_implements_validate(self):
        """Test LiteLLMNormalizer implements validate method."""
        normalizer = LiteLLMNormalizer(models=[])

        assert hasattr(normalizer, "validate")

        result = await normalizer.validate("AB", None, None)
        assert result is not None

    @pytest.mark.asyncio
    async def test_implements_validate_batch(self):
        """Test LiteLLMNormalizer implements validate_batch method."""
        normalizer = LiteLLMNormalizer(models=[])

        assert hasattr(normalizer, "validate_batch")

        results = await normalizer.validate_batch([])
        assert results == []
