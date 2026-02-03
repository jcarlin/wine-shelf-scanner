"""
Tests for Claude Vision service.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from app.services.claude_vision import (
    _build_vision_prompt,
    _build_single_bottle_prompt,
    _parse_vision_response,
    _parse_single_bottle_response,
    VisionIdentifiedWine,
    ClaudeVisionService,
)
from app.services.ocr_processor import BottleText
from app.services.vision import DetectedObject, BoundingBox as VisionBBox


def create_mock_bottle_text(
    x: float = 0.1,
    y: float = 0.1,
    width: float = 0.2,
    height: float = 0.3,
    text: str = "Test Wine",
) -> BottleText:
    """Create a mock BottleText for testing."""
    bottle = DetectedObject(
        name="Bottle",
        confidence=0.95,
        bbox=VisionBBox(x=x, y=y, width=width, height=height),
    )
    return BottleText(
        bottle=bottle,
        text_fragments=[text],
        combined_text=text,
        normalized_name=text.lower(),
    )


class TestBuildVisionPrompt:
    """Tests for _build_vision_prompt function."""

    def test_includes_bottle_locations(self):
        """Test that prompt includes bottle location descriptions."""
        bottles = [
            create_mock_bottle_text(x=0.25, y=0.40, text="Caymus"),
            create_mock_bottle_text(x=0.50, y=0.40, text="Opus One"),
        ]

        prompt = _build_vision_prompt(bottles)

        assert "Bottle 0" in prompt
        assert "Bottle 1" in prompt
        assert "x=25%" in prompt
        assert "y=40%" in prompt
        assert "Caymus" in prompt
        assert "Opus One" in prompt

    def test_includes_ocr_hints(self):
        """Test that prompt includes OCR text hints."""
        bottles = [create_mock_bottle_text(text="La Crema Chardonnay")]

        prompt = _build_vision_prompt(bottles)

        assert 'OCR hint: "La Crema Chardonnay"' in prompt

    def test_handles_empty_ocr(self):
        """Test handling of bottles with no OCR text."""
        bottle = create_mock_bottle_text(text="")
        bottle.combined_text = None

        prompt = _build_vision_prompt([bottle])

        assert "no OCR text" in prompt


class TestBuildSingleBottlePrompt:
    """Tests for _build_single_bottle_prompt function."""

    def test_includes_ocr_hint_when_provided(self):
        """Test that OCR hint is included when provided."""
        prompt = _build_single_bottle_prompt("Caymus Cabernet")

        assert "OCR text hint" in prompt
        assert "Caymus Cabernet" in prompt

    def test_no_hint_when_none(self):
        """Test prompt without OCR hint."""
        prompt = _build_single_bottle_prompt(None)

        assert "OCR text hint" not in prompt

    def test_requests_json_response(self):
        """Test that prompt requests JSON format."""
        prompt = _build_single_bottle_prompt("test")

        assert "JSON object" in prompt
        assert '"wine_name"' in prompt


class TestParseVisionResponse:
    """Tests for _parse_vision_response function."""

    def test_parses_valid_json_array(self):
        """Test parsing a valid JSON response."""
        response = json.dumps([
            {
                "bottle_index": 0,
                "wine_name": "Caymus Cabernet",
                "confidence": 0.85,
                "estimated_rating": 4.5,
                "wine_type": "Red",
                "brand": "Caymus",
                "region": "Napa Valley",
                "varietal": "Cabernet Sauvignon",
                "blurb": "A rich, full-bodied wine",
                "reasoning": "Clear label visible",
            }
        ])

        results = _parse_vision_response(response, num_bottles=1)

        assert len(results) == 1
        wine = results[0]
        assert wine.bottle_index == 0
        assert wine.wine_name == "Caymus Cabernet"
        assert wine.confidence == 0.85
        assert wine.estimated_rating == 4.5
        assert wine.wine_type == "Red"
        assert wine.brand == "Caymus"
        assert wine.region == "Napa Valley"
        assert wine.varietal == "Cabernet Sauvignon"

    def test_handles_markdown_code_block(self):
        """Test parsing JSON wrapped in markdown code block."""
        response = """```json
[{"bottle_index": 0, "wine_name": "Test Wine", "confidence": 0.7, "reasoning": "test"}]
```"""

        results = _parse_vision_response(response, num_bottles=1)

        assert len(results) == 1
        assert results[0].wine_name == "Test Wine"

    def test_handles_null_values(self):
        """Test parsing response with null values."""
        response = json.dumps([
            {
                "bottle_index": 0,
                "wine_name": None,
                "confidence": 0.0,
                "estimated_rating": None,
                "wine_type": None,
                "brand": None,
                "region": None,
                "varietal": None,
                "blurb": None,
                "reasoning": "Could not identify",
            }
        ])

        results = _parse_vision_response(response, num_bottles=1)

        assert len(results) == 1
        assert results[0].wine_name is None
        assert results[0].estimated_rating is None

    def test_filters_invalid_bottle_indices(self):
        """Test that out-of-range bottle indices are filtered."""
        response = json.dumps([
            {"bottle_index": 0, "wine_name": "Wine 1", "confidence": 0.8, "reasoning": "test"},
            {"bottle_index": 5, "wine_name": "Wine 2", "confidence": 0.8, "reasoning": "test"},  # Out of range
            {"bottle_index": -1, "wine_name": "Wine 3", "confidence": 0.8, "reasoning": "test"},  # Negative
        ])

        results = _parse_vision_response(response, num_bottles=2)

        assert len(results) == 1
        assert results[0].bottle_index == 0

    def test_handles_invalid_json(self):
        """Test handling of invalid JSON."""
        results = _parse_vision_response("not valid json", num_bottles=1)
        assert results == []

    def test_handles_non_list_response(self):
        """Test handling of non-list JSON."""
        response = json.dumps({"error": "something went wrong"})
        results = _parse_vision_response(response, num_bottles=1)
        assert results == []


class TestParseSingleBottleResponse:
    """Tests for _parse_single_bottle_response function."""

    def test_parses_valid_single_object(self):
        """Test parsing a valid single bottle response."""
        response = json.dumps({
            "wine_name": "Yellow Tail Shiraz",
            "confidence": 0.75,
            "estimated_rating": 3.8,
            "wine_type": "Red",
            "brand": "Yellow Tail",
            "region": "South Eastern Australia",
            "varietal": "Shiraz",
            "blurb": "Easy drinking Australian red",
            "reasoning": "Distinctive kangaroo logo",
        })

        result = _parse_single_bottle_response(response, bottle_index=2)

        assert result is not None
        assert result.bottle_index == 2  # Uses provided index
        assert result.wine_name == "Yellow Tail Shiraz"
        assert result.confidence == 0.75
        assert result.estimated_rating == 3.8

    def test_handles_markdown_wrapper(self):
        """Test parsing with markdown code block."""
        response = """```json
{"wine_name": "Test", "confidence": 0.6, "reasoning": "test"}
```"""

        result = _parse_single_bottle_response(response, bottle_index=0)

        assert result is not None
        assert result.wine_name == "Test"

    def test_returns_none_on_invalid_json(self):
        """Test that invalid JSON returns None."""
        result = _parse_single_bottle_response("invalid", bottle_index=0)
        assert result is None

    def test_returns_none_on_list_response(self):
        """Test that list response returns None (expects object)."""
        response = json.dumps([{"wine_name": "Test"}])
        result = _parse_single_bottle_response(response, bottle_index=0)
        assert result is None


class TestClaudeVisionService:
    """Tests for ClaudeVisionService class."""

    def test_default_model(self):
        """Test default model is set."""
        service = ClaudeVisionService()
        assert service.model == ClaudeVisionService.DEFAULT_MODEL

    def test_custom_model(self):
        """Test custom model can be set."""
        service = ClaudeVisionService(model="claude-3-haiku-20240307")
        assert service.model == "claude-3-haiku-20240307"

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_bottles(self):
        """Test that empty list returns empty results."""
        service = ClaudeVisionService()
        results = await service.identify_wines(b"image", [])
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_anthropic_unavailable(self):
        """Test graceful handling when anthropic is not installed."""
        with patch("app.services.claude_vision.ANTHROPIC_AVAILABLE", False):
            service = ClaudeVisionService()
            bottles = [create_mock_bottle_text()]
            results = await service.identify_wines(b"image", bottles)
            assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_api_key(self):
        """Test graceful handling when API key is not set."""
        with patch("app.services.claude_vision.Config.anthropic_api_key", return_value=None):
            service = ClaudeVisionService()
            bottles = [create_mock_bottle_text()]
            results = await service.identify_wines(b"image", bottles)
            assert results == []


class TestVisionIdentifiedWine:
    """Tests for VisionIdentifiedWine dataclass."""

    def test_dataclass_fields(self):
        """Test that all expected fields are present."""
        wine = VisionIdentifiedWine(
            bottle_index=0,
            wine_name="Test Wine",
            confidence=0.85,
            estimated_rating=4.2,
            wine_type="Red",
            brand="Test Brand",
            region="Test Region",
            varietal="Test Varietal",
            blurb="A test wine",
            reasoning="Test reasoning",
        )

        assert wine.bottle_index == 0
        assert wine.wine_name == "Test Wine"
        assert wine.confidence == 0.85
        assert wine.estimated_rating == 4.2
        assert wine.wine_type == "Red"
        assert wine.brand == "Test Brand"
        assert wine.region == "Test Region"
        assert wine.varietal == "Test Varietal"
        assert wine.blurb == "A test wine"
        assert wine.reasoning == "Test reasoning"
