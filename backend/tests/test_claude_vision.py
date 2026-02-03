"""
Tests for Claude Vision service.

Tests the ClaudeVisionService and MockClaudeVisionService implementations.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from app.services.claude_vision import (
    ClaudeVisionService,
    MockClaudeVisionService,
    ClaudeVisionResult,
    WineDetection,
    get_vision_service,
    WINE_SHELF_ANALYSIS_PROMPT,
)
from app.services.vision import VisionResult, BoundingBox, DetectedObject, TextBlock


class TestMockClaudeVisionService:
    """Tests for MockClaudeVisionService."""

    def test_full_shelf_scenario(self):
        """Test full shelf mock returns 8 wines."""
        service = MockClaudeVisionService(scenario="full_shelf")
        result = service.analyze(b"fake image")

        assert isinstance(result, VisionResult)
        assert len(result.objects) == 8
        assert len(result.text_blocks) == 8
        assert result.raw_text  # Should have combined text

    def test_partial_scenario(self):
        """Test partial scenario returns 3 wines."""
        service = MockClaudeVisionService(scenario="partial")
        result = service.analyze(b"fake image")

        assert len(result.objects) == 3
        assert len(result.text_blocks) == 3

    def test_empty_scenario(self):
        """Test empty scenario returns no wines."""
        service = MockClaudeVisionService(scenario="empty")
        result = service.analyze(b"fake image")

        assert len(result.objects) == 0
        assert len(result.text_blocks) == 0

    def test_detailed_result(self):
        """Test analyze_detailed returns ClaudeVisionResult."""
        service = MockClaudeVisionService(scenario="full_shelf")
        result = service.analyze_detailed(b"fake image")

        assert isinstance(result, ClaudeVisionResult)
        assert len(result.wines) == 8
        assert result.total_bottles == 8
        assert result.image_quality == "good"

        # Check first wine details
        first_wine = result.wines[0]
        assert isinstance(first_wine, WineDetection)
        assert first_wine.wine_name == "Caymus Cabernet Sauvignon"
        assert first_wine.confidence >= 0.9
        assert first_wine.bbox.x >= 0
        assert first_wine.bbox.width > 0

    def test_mock_wine_names(self):
        """Test mock returns expected wine names."""
        service = MockClaudeVisionService(scenario="full_shelf")
        result = service.analyze_detailed(b"fake image")

        wine_names = [w.wine_name for w in result.wines]
        assert "Caymus Cabernet Sauvignon" in wine_names
        assert "Opus One" in wine_names
        assert "Silver Oak Alexander Valley" in wine_names

    def test_text_blocks_contain_wine_names(self):
        """Test text blocks contain normalized wine names (not raw OCR)."""
        service = MockClaudeVisionService(scenario="full_shelf")
        result = service.analyze(b"fake image")

        # Text blocks should contain clean wine names for pipeline
        text_contents = [tb.text for tb in result.text_blocks]
        assert "Caymus Cabernet Sauvignon" in text_contents
        assert "Opus One" in text_contents


class TestClaudeVisionService:
    """Tests for ClaudeVisionService."""

    def test_init_without_api_key(self):
        """Test service initializes without API key."""
        with patch.dict('os.environ', {}, clear=True):
            service = ClaudeVisionService(api_key=None)
            assert service.api_key is None

    def test_init_with_api_key(self):
        """Test service initializes with provided API key."""
        service = ClaudeVisionService(api_key="test-key")
        assert service.api_key == "test-key"

    def test_init_with_env_api_key(self):
        """Test service reads API key from environment."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'env-key'}):
            service = ClaudeVisionService()
            assert service.api_key == "env-key"

    def test_default_model(self):
        """Test default model is claude-sonnet-4."""
        service = ClaudeVisionService()
        assert "sonnet" in service.model.lower() or "claude" in service.model.lower()

    def test_haiku_model_option(self):
        """Test Haiku model can be selected."""
        service = ClaudeVisionService(use_haiku=True)
        assert "haiku" in service.model.lower()

    def test_custom_model(self):
        """Test custom model can be specified."""
        service = ClaudeVisionService(model="custom-model-123")
        assert service.model == "custom-model-123"

    def test_analyze_without_api_key_returns_empty(self):
        """Test analyze returns empty result without API key."""
        with patch.dict('os.environ', {}, clear=True):
            service = ClaudeVisionService(api_key=None)
            result = service.analyze(b"fake image")

            assert isinstance(result, VisionResult)
            assert len(result.objects) == 0
            assert len(result.text_blocks) == 0

    def test_detect_media_type_jpeg(self):
        """Test JPEG detection."""
        service = ClaudeVisionService()
        # JPEG magic bytes
        jpeg_bytes = b'\xff\xd8\xff\xe0' + b'\x00' * 100
        assert service._detect_media_type(jpeg_bytes) == "image/jpeg"

    def test_detect_media_type_png(self):
        """Test PNG detection."""
        service = ClaudeVisionService()
        # PNG magic bytes
        png_bytes = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        assert service._detect_media_type(png_bytes) == "image/png"

    def test_detect_media_type_gif(self):
        """Test GIF detection."""
        service = ClaudeVisionService()
        gif_bytes = b'GIF89a' + b'\x00' * 100
        assert service._detect_media_type(gif_bytes) == "image/gif"

    def test_detect_media_type_unknown_defaults_to_jpeg(self):
        """Test unknown format defaults to JPEG."""
        service = ClaudeVisionService()
        unknown_bytes = b'\x00\x00\x00\x00' + b'\x00' * 100
        assert service._detect_media_type(unknown_bytes) == "image/jpeg"

    def test_bbox_to_position_left(self):
        """Test position conversion for left side."""
        service = ClaudeVisionService()
        bbox = BoundingBox(x=0.1, y=0.5, width=0.1, height=0.3)
        assert "left" in service._bbox_to_position(bbox)

    def test_bbox_to_position_center(self):
        """Test position conversion for center."""
        service = ClaudeVisionService()
        bbox = BoundingBox(x=0.45, y=0.45, width=0.1, height=0.1)
        assert service._bbox_to_position(bbox) == "center"

    def test_bbox_to_position_right(self):
        """Test position conversion for right side."""
        service = ClaudeVisionService()
        bbox = BoundingBox(x=0.8, y=0.5, width=0.1, height=0.3)
        assert "right" in service._bbox_to_position(bbox)

    def test_parse_response_valid_json(self):
        """Test parsing valid JSON response."""
        service = ClaudeVisionService()
        response = json.dumps({
            "wines": [
                {
                    "wine_name": "Test Wine",
                    "raw_text": "TEST WINE 2021",
                    "bbox": {"x": 0.1, "y": 0.2, "width": 0.1, "height": 0.3},
                    "confidence": 0.9
                }
            ],
            "total_bottles": 1,
            "raw_ocr_text": "TEST WINE 2021",
            "image_quality": "good"
        })

        result = service._parse_response(response)

        assert isinstance(result, ClaudeVisionResult)
        assert len(result.wines) == 1
        assert result.wines[0].wine_name == "Test Wine"
        assert result.wines[0].confidence == 0.9
        assert result.total_bottles == 1

    def test_parse_response_with_markdown_wrapper(self):
        """Test parsing JSON wrapped in markdown code block."""
        service = ClaudeVisionService()
        response = """```json
{
    "wines": [{"wine_name": "Test", "raw_text": "TEST", "bbox": {"x": 0.1, "y": 0.2, "width": 0.1, "height": 0.3}, "confidence": 0.8}],
    "total_bottles": 1,
    "raw_ocr_text": "TEST",
    "image_quality": "fair"
}
```"""

        result = service._parse_response(response)
        assert len(result.wines) == 1
        assert result.wines[0].wine_name == "Test"

    def test_parse_response_invalid_json(self):
        """Test parsing invalid JSON returns empty result."""
        service = ClaudeVisionService()
        result = service._parse_response("not valid json at all")

        assert isinstance(result, ClaudeVisionResult)
        assert len(result.wines) == 0
        assert result.total_bottles == 0

    def test_parse_response_creates_compatible_objects(self):
        """Test parsed response includes compatible DetectedObject and TextBlock."""
        service = ClaudeVisionService()
        response = json.dumps({
            "wines": [
                {
                    "wine_name": "Caymus Cabernet",
                    "raw_text": "CAYMUS",
                    "bbox": {"x": 0.15, "y": 0.2, "width": 0.1, "height": 0.35},
                    "confidence": 0.92
                }
            ],
            "total_bottles": 1,
            "raw_ocr_text": "CAYMUS",
            "image_quality": "good"
        })

        result = service._parse_response(response)

        # Check objects (bottles)
        assert len(result.objects) == 1
        assert isinstance(result.objects[0], DetectedObject)
        assert result.objects[0].name == "Bottle"
        assert result.objects[0].confidence == 0.92

        # Check text blocks (normalized wine names)
        assert len(result.text_blocks) == 1
        assert isinstance(result.text_blocks[0], TextBlock)
        assert result.text_blocks[0].text == "Caymus Cabernet"  # Normalized name!

    @patch('app.services.claude_vision.ANTHROPIC_AVAILABLE', True)
    def test_analyze_with_mock_client(self):
        """Test analyze with mocked Anthropic client."""
        service = ClaudeVisionService(api_key="test-key")

        # Mock the client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "wines": [
                {
                    "wine_name": "Opus One",
                    "raw_text": "OPUS ONE NAPA VALLEY",
                    "bbox": {"x": 0.2, "y": 0.15, "width": 0.1, "height": 0.35},
                    "confidence": 0.95
                }
            ],
            "total_bottles": 1,
            "raw_ocr_text": "OPUS ONE NAPA VALLEY",
            "image_quality": "good"
        }))]
        mock_client.messages.create.return_value = mock_response
        service._client = mock_client

        result = service.analyze(b'\xff\xd8\xff' + b'\x00' * 100)

        assert isinstance(result, VisionResult)
        assert len(result.objects) == 1
        assert len(result.text_blocks) == 1
        # Text blocks contain normalized wine names from Claude
        assert result.text_blocks[0].text == "Opus One"


class TestGetVisionService:
    """Tests for get_vision_service factory function."""

    def test_get_google_vision_service(self):
        """Test factory returns Google Vision service."""
        with patch('app.services.vision.VisionService') as mock:
            mock.return_value = MagicMock()
            service = get_vision_service(provider="google", use_mock=False)
            mock.assert_called_once()

    def test_get_google_mock_service(self):
        """Test factory returns mock Google Vision service."""
        from app.services.vision import MockVisionService as GoogleMock
        service = get_vision_service(provider="google", use_mock=True, mock_scenario="partial")
        assert isinstance(service, GoogleMock)

    def test_get_claude_vision_service(self):
        """Test factory returns Claude Vision service."""
        service = get_vision_service(provider="claude", use_mock=False)
        assert isinstance(service, ClaudeVisionService)

    def test_get_claude_mock_service(self):
        """Test factory returns mock Claude Vision service."""
        service = get_vision_service(provider="claude", use_mock=True, mock_scenario="full_shelf")
        assert isinstance(service, MockClaudeVisionService)

    def test_default_provider_is_google(self):
        """Test default provider is Google."""
        from app.services.vision import MockVisionService as GoogleMock
        service = get_vision_service(use_mock=True)
        assert isinstance(service, GoogleMock)


class TestPromptContent:
    """Tests for the analysis prompt."""

    def test_prompt_includes_json_format(self):
        """Test prompt asks for JSON format."""
        assert "JSON" in WINE_SHELF_ANALYSIS_PROMPT
        assert "wine_name" in WINE_SHELF_ANALYSIS_PROMPT
        assert "bbox" in WINE_SHELF_ANALYSIS_PROMPT

    def test_prompt_includes_extraction_rules(self):
        """Test prompt includes wine name extraction rules."""
        assert "REMOVE" in WINE_SHELF_ANALYSIS_PROMPT
        assert "vintage" in WINE_SHELF_ANALYSIS_PROMPT.lower()
        assert "750ml" in WINE_SHELF_ANALYSIS_PROMPT

    def test_prompt_includes_confidence_scale(self):
        """Test prompt includes confidence scale."""
        assert "0.90" in WINE_SHELF_ANALYSIS_PROMPT
        assert "confidence" in WINE_SHELF_ANALYSIS_PROMPT.lower()

    def test_prompt_includes_position_guidance(self):
        """Test prompt includes position estimation guidance."""
        assert "normalized coordinates" in WINE_SHELF_ANALYSIS_PROMPT.lower()
        assert "0-1" in WINE_SHELF_ANALYSIS_PROMPT


class TestIntegrationWithPipeline:
    """Tests for integration with the recognition pipeline."""

    def test_vision_result_compatibility(self):
        """Test VisionResult from Claude is compatible with OCR processor."""
        from app.services.ocr_processor import OCRProcessor

        service = MockClaudeVisionService(scenario="full_shelf")
        vision_result = service.analyze(b"fake image")

        # OCR processor should work with Claude Vision result
        processor = OCRProcessor()
        bottle_texts = processor.process(
            vision_result.objects,
            vision_result.text_blocks
        )

        # Should have processed bottles
        assert len(bottle_texts) > 0

        # Bottle texts should have normalized names (from Claude)
        for bt in bottle_texts:
            assert bt.normalized_name  # Should be non-empty
            # Names should be clean (no years, sizes)
            assert "2021" not in bt.normalized_name
            assert "750ml" not in bt.normalized_name.lower()

    def test_claude_vision_text_blocks_are_already_normalized(self):
        """Test that Claude Vision text blocks contain normalized names."""
        service = MockClaudeVisionService(scenario="full_shelf")
        result = service.analyze(b"fake image")

        # Text blocks from Claude Vision contain clean wine names
        for tb in result.text_blocks:
            # Should not contain typical OCR noise
            assert not any(year in tb.text for year in ["2019", "2020", "2021", "2022"])
            assert "ml" not in tb.text.lower()
            # Should be reasonable length (wine name, not OCR garbage)
            assert len(tb.text) < 100
