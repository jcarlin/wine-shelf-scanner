"""
Tests for OCR processor.
"""

import pytest
from app.services.ocr_processor import OCRProcessor
from app.services.vision import DetectedObject, TextBlock, BoundingBox


class TestOCRProcessor:
    """Tests for OCR text processing."""

    def test_normalize_removes_years(self):
        processor = OCRProcessor()

        result = processor._normalize_text("Caymus Cabernet Sauvignon 2021")
        assert "2021" not in result
        assert "Caymus" in result

        result = processor._normalize_text("Opus One 2019 Napa Valley")
        assert "2019" not in result

    def test_normalize_removes_sizes(self):
        processor = OCRProcessor()

        result = processor._normalize_text("Caymus 750ml Cabernet")
        assert "750ml" not in result.lower()
        assert "750" not in result

        result = processor._normalize_text("Opus One 1.5L Magnum")
        assert "1.5L" not in result
        assert "1.5l" not in result.lower()

    def test_normalize_removes_prices(self):
        processor = OCRProcessor()

        result = processor._normalize_text("Caymus $49.99 Cabernet")
        assert "$49.99" not in result
        assert "49" not in result

    def test_normalize_removes_abv(self):
        processor = OCRProcessor()

        result = processor._normalize_text("Caymus 14.5% alc Cabernet")
        assert "14.5" not in result
        assert "alc" not in result.lower()

    def test_normalize_removes_filler_words(self):
        processor = OCRProcessor()

        result = processor._normalize_text("Reserve Special Edition Caymus Estate")
        assert "reserve" not in result.lower()
        assert "special" not in result.lower()
        assert "edition" not in result.lower()
        assert "estate" not in result.lower()
        assert "Caymus" in result

    def test_normalize_title_cases(self):
        processor = OCRProcessor()

        result = processor._normalize_text("caymus cabernet sauvignon")
        assert result == "Caymus Cabernet Sauvignon"

    def test_group_text_to_bottles(self):
        processor = OCRProcessor()

        bottles = [
            DetectedObject("Bottle", 0.95, BoundingBox(0.1, 0.2, 0.1, 0.3)),
            DetectedObject("Bottle", 0.90, BoundingBox(0.4, 0.2, 0.1, 0.3)),
        ]

        text_blocks = [
            TextBlock("CAYMUS", BoundingBox(0.12, 0.25, 0.06, 0.04), 0.9),
            TextBlock("Cabernet", BoundingBox(0.11, 0.30, 0.08, 0.03), 0.9),
            TextBlock("OPUS", BoundingBox(0.42, 0.25, 0.06, 0.04), 0.9),
            TextBlock("ONE", BoundingBox(0.42, 0.30, 0.04, 0.03), 0.9),
        ]

        result = processor.process(bottles, text_blocks)

        assert len(result) == 2
        # First bottle should have Caymus text
        assert "Caymus" in result[0].normalized_name or "Cabernet" in result[0].normalized_name
        # Second bottle should have Opus One text
        assert "Opus" in result[1].normalized_name or "One" in result[1].normalized_name

    def test_process_empty_bottles(self):
        processor = OCRProcessor()
        result = processor.process([], [])
        assert result == []

    def test_process_bottles_no_text(self):
        processor = OCRProcessor()

        bottles = [
            DetectedObject("Bottle", 0.95, BoundingBox(0.1, 0.2, 0.1, 0.3)),
        ]

        result = processor.process(bottles, [])

        assert len(result) == 1
        assert result[0].normalized_name == ""
