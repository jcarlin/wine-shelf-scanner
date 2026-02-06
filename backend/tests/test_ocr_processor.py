"""
Tests for OCR processor.
"""

import pytest
from app.services.ocr_processor import OCRProcessor, OCRProcessingResult, OrphanedText
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
        # "special" and "edition" are marketing filler — removed
        assert "special" not in result.lower()
        assert "edition" not in result.lower()
        # "reserve" and "estate" are wine-identity words — kept
        assert "reserve" in result.lower()
        assert "estate" in result.lower()
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


class TestOCRProcessorOrphanedText:
    """Tests for orphaned text handling."""

    def test_process_with_orphans_returns_both(self):
        """Test that process_with_orphans returns bottle texts and orphaned texts."""
        processor = OCRProcessor()

        bottles = [
            DetectedObject("Bottle", 0.95, BoundingBox(0.1, 0.2, 0.1, 0.3)),
        ]

        text_blocks = [
            # Near the bottle
            TextBlock("CAYMUS", BoundingBox(0.12, 0.25, 0.06, 0.04), 0.9),
            # Far from any bottle (orphaned)
            TextBlock("Merlot", BoundingBox(0.8, 0.8, 0.06, 0.04), 0.9),
        ]

        result = processor.process_with_orphans(bottles, text_blocks)

        assert isinstance(result, OCRProcessingResult)
        assert len(result.bottle_texts) == 1
        assert "Caymus" in result.bottle_texts[0].normalized_name
        # Orphaned text should be captured
        assert len(result.orphaned_texts) >= 1
        orphan_names = [o.normalized_name for o in result.orphaned_texts]
        assert any("Merlot" in name for name in orphan_names)

    def test_process_with_orphans_no_bottles(self):
        """When no bottles detected, all text becomes orphaned."""
        processor = OCRProcessor()

        text_blocks = [
            TextBlock("Cabernet", BoundingBox(0.1, 0.2, 0.06, 0.04), 0.9),
            TextBlock("Merlot", BoundingBox(0.5, 0.5, 0.06, 0.04), 0.9),
        ]

        result = processor.process_with_orphans([], text_blocks)

        assert len(result.bottle_texts) == 0
        assert len(result.orphaned_texts) == 2

    def test_process_with_orphans_all_text_assigned(self):
        """When all text is near bottles, no orphans."""
        processor = OCRProcessor()

        bottles = [
            DetectedObject("Bottle", 0.95, BoundingBox(0.1, 0.2, 0.15, 0.35)),
            DetectedObject("Bottle", 0.90, BoundingBox(0.4, 0.2, 0.15, 0.35)),
        ]

        text_blocks = [
            TextBlock("CAYMUS", BoundingBox(0.12, 0.25, 0.06, 0.04), 0.9),
            TextBlock("OPUS ONE", BoundingBox(0.42, 0.25, 0.08, 0.04), 0.9),
        ]

        result = processor.process_with_orphans(bottles, text_blocks)

        assert len(result.bottle_texts) == 2
        assert len(result.orphaned_texts) == 0

    def test_orphaned_text_filters_short_text(self):
        """Orphaned text blocks with short normalized names are filtered out."""
        processor = OCRProcessor()

        text_blocks = [
            TextBlock("AB", BoundingBox(0.5, 0.5, 0.02, 0.02), 0.9),  # Too short
            TextBlock("Cabernet Sauvignon", BoundingBox(0.8, 0.8, 0.1, 0.04), 0.9),
        ]

        result = processor.process_with_orphans([], text_blocks)

        # Only the longer text should be in orphans
        assert len(result.orphaned_texts) == 1
        assert "Cabernet" in result.orphaned_texts[0].normalized_name


class TestProcessOrphanedTexts:
    """Tests for _process_orphaned_texts helper in scan route."""

    def test_process_orphaned_texts_returns_fallback_wines(self):
        """Test that orphaned texts are matched and returned as FallbackWine."""
        from app.routes.scan import _process_orphaned_texts
        from app.models import FallbackWine
        from app.services.wine_matcher import WineMatcher

        wine_matcher = WineMatcher(use_sqlite=True)

        orphaned_texts = [
            OrphanedText(
                text="Caymus Cabernet",
                normalized_name="Caymus Cabernet",
                bbox=BoundingBox(0.5, 0.5, 0.1, 0.1)
            )
        ]

        result = _process_orphaned_texts(orphaned_texts, wine_matcher)

        # Should return a list of FallbackWine
        assert isinstance(result, list)
        # If matched, should have FallbackWine objects with wine_name and rating
        for wine in result:
            assert isinstance(wine, FallbackWine)
            assert hasattr(wine, 'wine_name')
            assert hasattr(wine, 'rating')

    def test_process_orphaned_texts_deduplicates(self):
        """Test that duplicate orphaned texts are deduplicated."""
        from app.routes.scan import _process_orphaned_texts
        from app.services.wine_matcher import WineMatcher

        wine_matcher = WineMatcher(use_sqlite=True)

        orphaned_texts = [
            OrphanedText(
                text="Caymus",
                normalized_name="Caymus",
                bbox=BoundingBox(0.3, 0.3, 0.1, 0.1)
            ),
            OrphanedText(
                text="CAYMUS",
                normalized_name="Caymus",
                bbox=BoundingBox(0.7, 0.7, 0.1, 0.1)
            ),
        ]

        result = _process_orphaned_texts(orphaned_texts, wine_matcher)

        # Should deduplicate - only one match even if text appears twice
        wine_names = [w.wine_name for w in result]
        assert len(wine_names) == len(set(wine_names))
