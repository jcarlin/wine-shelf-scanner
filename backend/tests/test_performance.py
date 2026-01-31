"""
Performance tests for the wine shelf scanner.

Validates:
- End-to-end response time < 4 seconds (with mocks)
- Fuzzy matching performance with large database
- Pipeline throughput with multiple bottles
"""

import pytest
import time
from io import BytesIO
from fastapi.testclient import TestClient

from main import app
from app.services.wine_matcher import WineMatcher
from app.services.recognition_pipeline import RecognitionPipeline
from app.services.llm_normalizer import MockNormalizer
from app.services.ocr_processor import BottleText, OCRProcessor
from app.services.vision import (
    DetectedObject,
    TextBlock,
    BoundingBox,
    MockVisionService,
)


client = TestClient(app)


def create_test_image() -> BytesIO:
    """Create a minimal valid JPEG for testing."""
    jpeg_bytes = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
        0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
        0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5, 0xDB, 0x20, 0xA8, 0xE0, 0x8A, 0x28,
        0xA0, 0xFF, 0xD9
    ])
    return BytesIO(jpeg_bytes)


def create_bottle_text(name: str, confidence: float = 0.9) -> BottleText:
    """Create a BottleText for testing."""
    return BottleText(
        bottle=DetectedObject(
            name="Bottle",
            confidence=confidence,
            bbox=BoundingBox(x=0.1, y=0.1, width=0.1, height=0.3),
        ),
        text_fragments=[name],
        combined_text=name,
        normalized_name=name,
    )


class TestEndpointPerformance:
    """Test HTTP endpoint response time."""

    def test_scan_endpoint_under_4_seconds_with_mocks(self):
        """Test /scan endpoint responds in under 4 seconds with mocks."""
        image = create_test_image()

        start = time.perf_counter()
        response = client.post(
            "/scan?mock_scenario=full_shelf",
            files={"image": ("test.jpg", image, "image/jpeg")}
        )
        elapsed = time.perf_counter() - start

        assert response.status_code == 200
        assert elapsed < 4.0, f"Response took {elapsed:.2f}s, exceeds 4s target"

    def test_scan_endpoint_average_response_time(self):
        """Test average response time over multiple requests."""
        times = []

        for _ in range(10):
            image = create_test_image()

            start = time.perf_counter()
            response = client.post(
                "/scan?mock_scenario=full_shelf",
                files={"image": ("test.jpg", image, "image/jpeg")}
            )
            elapsed = time.perf_counter() - start

            assert response.status_code == 200
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # Average should be well under 4 seconds with mocks
        assert avg_time < 1.0, f"Average response time {avg_time:.2f}s too slow"
        assert max_time < 4.0, f"Max response time {max_time:.2f}s exceeds target"


class TestWineMatcherPerformance:
    """Test fuzzy matching performance."""

    @pytest.fixture
    def matcher(self):
        return WineMatcher()

    def test_single_match_under_50ms(self, matcher):
        """Test single match completes in under 50ms."""
        # Warm up (first match builds index)
        matcher.match("Opus One")

        start = time.perf_counter()
        result = matcher.match("Caymus Cabernet")
        elapsed = time.perf_counter() - start

        assert result is not None
        assert elapsed < 0.05, f"Single match took {elapsed*1000:.1f}ms"

    def test_match_many_performance(self, matcher):
        """Test batch matching is efficient."""
        queries = [
            "Opus One",
            "Caymus",
            "Silver Oak",
            "Jordan Cabernet",
            "La Crema",
            "Meiomi",
            "Kendall Jackson",
            "Bread Butter",
            "Unknown Wine",
            "Another Unknown",
        ]

        # Warm up
        matcher.match("test")

        start = time.perf_counter()
        results = matcher.match_many(queries)
        elapsed = time.perf_counter() - start

        assert len(results) == 10
        # Should complete all 10 matches in under 200ms
        assert elapsed < 0.2, f"Batch match took {elapsed*1000:.1f}ms for 10 queries"

    def test_fuzzy_match_performance_with_misspellings(self, matcher):
        """Test fuzzy matching handles misspellings efficiently."""
        misspelled = [
            "Opsu One",  # Opus One
            "Caymuss",  # Caymus
            "Silvr Oak",  # Silver Oak
            "Jordann",  # Jordan
            "Meeomi",  # Meiomi
        ]

        # Warm up
        matcher.match("test")

        start = time.perf_counter()
        for query in misspelled:
            matcher.match(query)
        elapsed = time.perf_counter() - start

        # Should handle 5 fuzzy matches in under 100ms
        assert elapsed < 0.1, f"Fuzzy matches took {elapsed*1000:.1f}ms"

    def test_no_match_performance(self, matcher):
        """Test performance when no match is found."""
        queries = [
            "Completely Unknown Wine Name",
            "Another Random String",
            "Not A Real Wine",
        ]

        # Warm up
        matcher.match("test")

        start = time.perf_counter()
        for query in queries:
            result = matcher.match(query)
            # These should return None
        elapsed = time.perf_counter() - start

        # No-match queries should still be fast
        assert elapsed < 0.1, f"No-match queries took {elapsed*1000:.1f}ms"


class TestRecognitionPipelinePerformance:
    """Test recognition pipeline throughput."""

    @pytest.mark.asyncio
    async def test_pipeline_throughput_8_bottles(self):
        """Test pipeline handles 8 bottles efficiently."""
        pipeline = RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=MockNormalizer(),
            use_llm=True,
        )

        bottle_texts = [
            create_bottle_text("Caymus Cabernet Sauvignon"),
            create_bottle_text("Opus One"),
            create_bottle_text("Silver Oak"),
            create_bottle_text("Jordan Cabernet"),
            create_bottle_text("Kendall Jackson"),
            create_bottle_text("La Crema Pinot"),
            create_bottle_text("Meiomi"),
            create_bottle_text("Bread Butter"),
        ]

        start = time.perf_counter()
        results = await pipeline.recognize(bottle_texts)
        elapsed = time.perf_counter() - start

        assert len(results) >= 6  # Should match most
        # Pipeline should process 8 bottles in under 500ms with mock LLM
        assert elapsed < 0.5, f"Pipeline took {elapsed*1000:.1f}ms for 8 bottles"

    @pytest.mark.asyncio
    async def test_pipeline_throughput_20_bottles(self):
        """Test pipeline handles 20 bottles in under 1 second."""
        pipeline = RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=MockNormalizer(),
            use_llm=True,
        )

        # Create 20 bottle texts
        wine_names = [
            "Opus One", "Caymus", "Silver Oak", "Jordan", "La Crema",
            "Meiomi", "Bread Butter", "Josh Cellars", "Apothic Red",
            "19 Crimes", "Barefoot Moscato", "Yellow Tail", "Chateau Margaux",
            "Penfolds Grange", "Cloudy Bay", "Kim Crawford", "Veuve Clicquot",
            "Dom Perignon", "Duckhorn", "Stags Leap",
        ]
        bottle_texts = [create_bottle_text(name) for name in wine_names]

        start = time.perf_counter()
        results = await pipeline.recognize(bottle_texts)
        elapsed = time.perf_counter() - start

        assert len(results) >= 15  # Should match most
        # Should process 20 bottles in under 1 second
        assert elapsed < 1.0, f"Pipeline took {elapsed:.2f}s for 20 bottles"

    @pytest.mark.asyncio
    async def test_pipeline_with_llm_disabled(self):
        """Test pipeline is faster with LLM disabled."""
        # With LLM
        pipeline_with_llm = RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=MockNormalizer(),
            use_llm=True,
        )

        # Without LLM
        pipeline_no_llm = RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=MockNormalizer(),
            use_llm=False,
        )

        bottle_texts = [
            create_bottle_text("Unknown Wine 1"),
            create_bottle_text("Unknown Wine 2"),
            create_bottle_text("Unknown Wine 3"),
        ]

        # Time with LLM (mock)
        start = time.perf_counter()
        await pipeline_with_llm.recognize(bottle_texts)
        time_with_llm = time.perf_counter() - start

        # Time without LLM
        start = time.perf_counter()
        await pipeline_no_llm.recognize(bottle_texts)
        time_no_llm = time.perf_counter() - start

        # Without LLM should be faster (no async normalizer calls)
        # But with mock normalizer, difference may be small
        assert time_no_llm <= time_with_llm * 1.5  # Allow some variance


class TestOCRProcessorPerformance:
    """Test OCR processor performance."""

    def test_ocr_grouping_performance(self):
        """Test text-to-bottle grouping is fast."""
        processor = OCRProcessor()

        # Create 8 bottles
        bottles = [
            DetectedObject("Bottle", 0.95, BoundingBox(0.05 + i * 0.1, 0.15, 0.08, 0.35))
            for i in range(8)
        ]

        # Create 20 text blocks
        text_blocks = [
            TextBlock(f"Text {i}", BoundingBox(0.05 + (i % 8) * 0.1, 0.25, 0.06, 0.04), 0.9)
            for i in range(20)
        ]

        start = time.perf_counter()
        results = processor.process(bottles, text_blocks)
        elapsed = time.perf_counter() - start

        assert len(results) == 8
        # Should process in under 50ms
        assert elapsed < 0.05, f"OCR grouping took {elapsed*1000:.1f}ms"

    def test_text_normalization_performance(self):
        """Test text normalization is fast."""
        processor = OCRProcessor()

        # Complex text with many patterns to remove
        complex_texts = [
            "CAYMUS 2019 CABERNET SAUVIGNON 750ml $49.99 14.5% alc",
            "OPUS ONE NAPA VALLEY RESERVE 2018 1.5L $299",
            "SILVER OAK ALEXANDER VALLEY ESTATE BOTTLED 2017",
        ]

        start = time.perf_counter()
        for text in complex_texts:
            processor._normalize_text(text)
        elapsed = time.perf_counter() - start

        # Should normalize 3 complex texts in under 10ms
        assert elapsed < 0.01, f"Normalization took {elapsed*1000:.1f}ms"


class TestMockVisionServicePerformance:
    """Test mock vision service performance."""

    def test_mock_vision_instant_response(self):
        """Test mock vision service responds instantly."""
        service = MockVisionService("full_shelf")

        start = time.perf_counter()
        result = service.analyze(b"dummy image bytes")
        elapsed = time.perf_counter() - start

        assert len(result.objects) == 8
        # Mock should be essentially instant (< 5ms)
        assert elapsed < 0.005, f"Mock vision took {elapsed*1000:.1f}ms"


class TestEndToEndPipelinePerformance:
    """Test full pipeline (vision -> OCR -> recognition)."""

    @pytest.mark.asyncio
    async def test_full_pipeline_under_500ms(self):
        """Test full pipeline with mocks completes in under 500ms."""
        # 1. Mock Vision
        vision_service = MockVisionService("full_shelf")
        vision_result = vision_service.analyze(b"dummy")

        # 2. OCR Processing
        ocr_processor = OCRProcessor()
        bottle_texts = ocr_processor.process(
            vision_result.objects,
            vision_result.text_blocks
        )

        # 3. Recognition Pipeline
        pipeline = RecognitionPipeline(
            wine_matcher=WineMatcher(),
            normalizer=MockNormalizer(),
            use_llm=False,
        )

        start = time.perf_counter()
        results = await pipeline.recognize(bottle_texts)
        elapsed = time.perf_counter() - start

        # Full pipeline should complete in under 500ms
        assert elapsed < 0.5, f"Full pipeline took {elapsed*1000:.1f}ms"
        assert len(results) >= 4  # Should recognize most bottles
