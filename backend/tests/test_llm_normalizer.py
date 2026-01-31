"""
Tests for the LLM normalizer service.

Tests:
- MockNormalizer behavior for predictable testing
- NormalizerProtocol interface compliance
- Normalization output format
- Error handling
- ClaudeNormalizer response parsing
"""

import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock

from app.services.llm_normalizer import (
    NormalizerProtocol,
    NormalizationResult,
    ClaudeNormalizer,
    MockNormalizer,
    get_normalizer,
    ANTHROPIC_AVAILABLE,
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


class TestClaudeNormalizerResponseParsing:
    """Test ClaudeNormalizer response parsing logic."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON response."""
        normalizer = ClaudeNormalizer.__new__(ClaudeNormalizer)
        normalizer.api_key = "test"

        response = '{"wine_name": "Opus One", "confidence": 0.9, "is_wine": true, "reasoning": "Clear label"}'
        result = normalizer._parse_response(response)

        assert result.wine_name == "Opus One"
        assert result.confidence == 0.9
        assert result.is_wine is True
        assert result.reasoning == "Clear label"

    def test_parse_json_with_markdown_code_block(self):
        """Test parsing JSON wrapped in markdown code block."""
        normalizer = ClaudeNormalizer.__new__(ClaudeNormalizer)
        normalizer.api_key = "test"

        response = """```json
{"wine_name": "Caymus", "confidence": 0.85, "is_wine": true, "reasoning": "Recognized brand"}
```"""
        result = normalizer._parse_response(response)

        assert result.wine_name == "Caymus"
        assert result.confidence == 0.85

    def test_parse_json_with_plain_code_block(self):
        """Test parsing JSON wrapped in plain code block."""
        normalizer = ClaudeNormalizer.__new__(ClaudeNormalizer)
        normalizer.api_key = "test"

        response = """```
{"wine_name": "Silver Oak", "confidence": 0.8, "is_wine": true, "reasoning": "Test"}
```"""
        result = normalizer._parse_response(response)

        assert result.wine_name == "Silver Oak"

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns error result."""
        normalizer = ClaudeNormalizer.__new__(ClaudeNormalizer)
        normalizer.api_key = "test"

        response = "This is not valid JSON"
        result = normalizer._parse_response(response)

        assert result.wine_name is None
        assert result.confidence == 0.0
        assert result.is_wine is False
        assert "Parse error" in result.reasoning

    def test_parse_missing_fields_uses_defaults(self):
        """Test parsing JSON with missing fields uses defaults."""
        normalizer = ClaudeNormalizer.__new__(ClaudeNormalizer)
        normalizer.api_key = "test"

        response = '{"wine_name": "Test Wine"}'
        result = normalizer._parse_response(response)

        assert result.wine_name == "Test Wine"
        assert result.confidence == 0.5  # Default
        assert result.is_wine is False  # Default
        assert result.reasoning == ""  # Default

    def test_parse_null_wine_name(self):
        """Test parsing JSON with null wine_name."""
        normalizer = ClaudeNormalizer.__new__(ClaudeNormalizer)
        normalizer.api_key = "test"

        response = '{"wine_name": null, "confidence": 0.0, "is_wine": false, "reasoning": "Not a wine"}'
        result = normalizer._parse_response(response)

        assert result.wine_name is None
        assert result.is_wine is False


class TestClaudeNormalizerEmptyInput:
    """Test ClaudeNormalizer handling of empty/short input."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_early(self):
        """Test empty text returns immediately without API call."""
        normalizer = ClaudeNormalizer(api_key="test")

        result = await normalizer.normalize("")

        assert result.wine_name is None
        assert result.confidence == 0.0
        assert result.is_wine is False
        assert "too short" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_early(self):
        """Test whitespace-only text returns immediately."""
        normalizer = ClaudeNormalizer(api_key="test")

        result = await normalizer.normalize("   \n\t  ")

        assert result.wine_name is None
        assert result.is_wine is False

    @pytest.mark.asyncio
    async def test_short_text_returns_early(self):
        """Test very short text (< 3 chars) returns immediately."""
        normalizer = ClaudeNormalizer(api_key="test")

        result = await normalizer.normalize("AB")

        assert result.wine_name is None
        assert result.is_wine is False


class TestClaudeNormalizerErrorHandling:
    """Test ClaudeNormalizer error handling."""

    @pytest.mark.asyncio
    async def test_missing_api_key_raises_error(self):
        """Test missing API key raises ValueError on client access."""
        normalizer = ClaudeNormalizer(api_key=None)
        # Clear any env var
        with patch.dict("os.environ", {}, clear=True):
            normalizer.api_key = None

            with pytest.raises(ValueError) as exc_info:
                normalizer._get_client()

            assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_api_error_returns_graceful_result(self):
        """Test API error returns graceful error result."""
        normalizer = ClaudeNormalizer(api_key="test")

        # Mock the client to raise an exception
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API Error")
        normalizer._client = mock_client

        result = await normalizer.normalize("Opus One Cabernet")

        assert result.wine_name is None
        assert result.confidence == 0.0
        assert result.is_wine is False
        # If anthropic isn't installed, we get "LLM not available"
        # If it is installed, we get "LLM error: Exception"
        if ANTHROPIC_AVAILABLE:
            assert "LLM error" in result.reasoning
        else:
            assert "LLM not available" in result.reasoning


class TestGetNormalizerFactory:
    """Test the get_normalizer factory function."""

    def test_returns_mock_when_use_mock_true(self):
        """Test factory returns MockNormalizer when use_mock=True."""
        normalizer = get_normalizer(use_mock=True)

        assert isinstance(normalizer, MockNormalizer)

    def test_returns_claude_when_use_mock_false(self):
        """Test factory returns ClaudeNormalizer when use_mock=False."""
        normalizer = get_normalizer(use_mock=False)

        assert isinstance(normalizer, ClaudeNormalizer)

    def test_default_returns_claude(self):
        """Test factory default returns ClaudeNormalizer."""
        normalizer = get_normalizer()

        assert isinstance(normalizer, ClaudeNormalizer)


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
    async def test_claude_normalizer_implements_protocol(self):
        """Test ClaudeNormalizer implements NormalizerProtocol."""
        normalizer = ClaudeNormalizer(api_key="test")

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
