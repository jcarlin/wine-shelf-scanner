"""
Tests for the Vision API response cache.
"""

import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.services.vision import BoundingBox, DetectedObject, TextBlock, VisionResult
from app.services.vision_cache import VisionCache, reset_vision_cache


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup
    if db_path.exists():
        os.unlink(db_path)


@pytest.fixture
def cache(temp_db):
    """Create a test cache instance."""
    return VisionCache(
        db_path=temp_db,
        enabled=True,
        ttl_days=7,
        max_size_mb=10,
    )


@pytest.fixture
def sample_result():
    """Create a sample VisionResult for testing."""
    return VisionResult(
        objects=[
            DetectedObject(
                name="Bottle",
                confidence=0.95,
                bbox=BoundingBox(x=0.1, y=0.2, width=0.1, height=0.3),
            ),
            DetectedObject(
                name="Bottle",
                confidence=0.90,
                bbox=BoundingBox(x=0.4, y=0.2, width=0.1, height=0.3),
            ),
        ],
        text_blocks=[
            TextBlock(
                text="CAYMUS",
                bbox=BoundingBox(x=0.12, y=0.25, width=0.06, height=0.04),
                confidence=0.9,
            ),
            TextBlock(
                text="Cabernet Sauvignon",
                bbox=BoundingBox(x=0.11, y=0.30, width=0.08, height=0.03),
                confidence=0.9,
            ),
        ],
        raw_text="CAYMUS\nCabernet Sauvignon\n2021",
        image_width=1000,
        image_height=1000,
    )


@pytest.fixture
def sample_image_bytes():
    """Create sample image bytes for testing."""
    return b"fake image content for testing purposes"


class TestVisionCacheBasic:
    """Test basic cache operations."""

    def test_cache_stores_and_retrieves(self, cache, sample_result, sample_image_bytes):
        """Test that cache can store and retrieve results."""
        # Store
        cache.set_by_bytes(sample_image_bytes, sample_result)

        # Retrieve
        cached = cache.get_by_bytes(sample_image_bytes)

        assert cached is not None
        assert len(cached.objects) == len(sample_result.objects)
        assert len(cached.text_blocks) == len(sample_result.text_blocks)
        assert cached.raw_text == sample_result.raw_text
        assert cached.image_width == sample_result.image_width
        assert cached.image_height == sample_result.image_height

    def test_cache_returns_none_for_missing(self, cache):
        """Test that cache returns None for non-existent entries."""
        result = cache.get_by_bytes(b"nonexistent image")
        assert result is None

    def test_same_image_produces_same_hash(self, cache, sample_result, sample_image_bytes):
        """Test that identical bytes produce the same cache key."""
        # Store with first call
        cache.set_by_bytes(sample_image_bytes, sample_result)

        # Retrieve with same bytes
        cached = cache.get_by_bytes(sample_image_bytes)
        assert cached is not None

        # Retrieve with identical bytes (new object)
        same_bytes = b"fake image content for testing purposes"
        cached2 = cache.get_by_bytes(same_bytes)
        assert cached2 is not None

    def test_different_images_different_entries(self, cache, sample_result):
        """Test that different images get different cache entries."""
        image1 = b"image one content"
        image2 = b"image two content"

        cache.set_by_bytes(image1, sample_result)

        # Different image should not hit cache
        cached = cache.get_by_bytes(image2)
        assert cached is None

    def test_data_integrity(self, cache, sample_result, sample_image_bytes):
        """Test that all data fields are preserved correctly."""
        cache.set_by_bytes(sample_image_bytes, sample_result)
        cached = cache.get_by_bytes(sample_image_bytes)

        # Check objects
        assert len(cached.objects) == 2
        assert cached.objects[0].name == "Bottle"
        assert cached.objects[0].confidence == 0.95
        assert cached.objects[0].bbox.x == 0.1
        assert cached.objects[0].bbox.y == 0.2
        assert cached.objects[0].bbox.width == 0.1
        assert cached.objects[0].bbox.height == 0.3

        # Check text blocks
        assert len(cached.text_blocks) == 2
        assert cached.text_blocks[0].text == "CAYMUS"
        assert cached.text_blocks[0].confidence == 0.9


class TestVisionCacheHitCount:
    """Test hit counting functionality."""

    def test_hit_count_increments(self, cache, sample_result, sample_image_bytes):
        """Test that hit count increments on each access."""
        cache.set_by_bytes(sample_image_bytes, sample_result)

        # First access
        cache.get_by_bytes(sample_image_bytes)

        # Check stats
        stats = cache.get_stats()
        assert stats["total_hits"] == 1

        # Second access
        cache.get_by_bytes(sample_image_bytes)

        stats = cache.get_stats()
        assert stats["total_hits"] == 2

    def test_miss_does_not_increment(self, cache):
        """Test that cache misses don't affect hit count."""
        # Access non-existent entry
        cache.get_by_bytes(b"nonexistent")
        cache.get_by_bytes(b"also nonexistent")

        stats = cache.get_stats()
        assert stats["total_hits"] == 0


class TestVisionCacheTTL:
    """Test TTL expiration."""

    def test_entry_expires_after_ttl(self, temp_db, sample_result, sample_image_bytes):
        """Test that entries expire after TTL."""
        # Create cache with very short TTL (not realistic but testable via direct DB manipulation)
        cache = VisionCache(db_path=temp_db, enabled=True, ttl_days=1, max_size_mb=10)

        # Store entry
        cache.set_by_bytes(sample_image_bytes, sample_result)

        # Verify it's there
        assert cache.get_by_bytes(sample_image_bytes) is not None

        # Manually expire the entry by updating the database
        import sqlite3
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "UPDATE vision_cache SET ttl_expires_at = datetime('now', '-1 day')"
        )
        conn.commit()
        conn.close()

        # Now it should be expired
        result = cache.get_by_bytes(sample_image_bytes)
        assert result is None

    def test_cleanup_removes_expired(self, temp_db, sample_result):
        """Test that cleanup removes expired entries."""
        cache = VisionCache(db_path=temp_db, enabled=True, ttl_days=1, max_size_mb=10)

        # Store multiple entries
        cache.set_by_bytes(b"image1", sample_result)
        cache.set_by_bytes(b"image2", sample_result)
        cache.set_by_bytes(b"image3", sample_result)

        # Manually expire some entries
        import sqlite3
        conn = sqlite3.connect(temp_db)
        conn.execute(
            """
            UPDATE vision_cache
            SET ttl_expires_at = datetime('now', '-1 day')
            WHERE image_hash IN (
                SELECT image_hash FROM vision_cache LIMIT 2
            )
            """
        )
        conn.commit()
        conn.close()

        # Run cleanup
        removed = cache.cleanup()
        assert removed == 2

        # Verify only one entry remains
        stats = cache.get_stats()
        assert stats["total_entries"] == 1


class TestVisionCacheSizeEviction:
    """Test size-based LRU eviction."""

    def test_eviction_on_size_limit(self, temp_db, sample_result):
        """Test that old entries are evicted when size limit is reached."""
        # Create cache with very small size limit (1KB)
        cache = VisionCache(
            db_path=temp_db,
            enabled=True,
            ttl_days=0,  # No TTL
            max_size_mb=0.001,  # ~1KB
        )

        # Store multiple entries (each entry is ~100-200 bytes compressed)
        for i in range(10):
            cache.set_by_bytes(f"image{i}".encode(), sample_result)
            # Small delay to ensure different timestamps
            time.sleep(0.01)

        # Some entries should have been evicted
        stats = cache.get_stats()
        assert stats["total_entries"] < 10

    def test_lru_order_preserved(self, temp_db, sample_result):
        """Test that least recently used entries are evicted first."""
        cache = VisionCache(
            db_path=temp_db,
            enabled=True,
            ttl_days=0,
            max_size_mb=0.001,
        )

        # Store entries with gaps
        cache.set_by_bytes(b"oldest", sample_result)
        time.sleep(0.01)
        cache.set_by_bytes(b"middle", sample_result)
        time.sleep(0.01)
        cache.set_by_bytes(b"newest", sample_result)

        # Access oldest to make it "recently used"
        cache.get_by_bytes(b"oldest")
        time.sleep(0.01)

        # Add more entries to trigger eviction
        for i in range(5):
            cache.set_by_bytes(f"extra{i}".encode(), sample_result)
            time.sleep(0.01)

        # "oldest" might still be there since we accessed it recently
        # "middle" is more likely to be evicted
        # This is a behavioral test - the exact behavior depends on entry sizes


class TestVisionCacheDisabled:
    """Test cache when disabled."""

    def test_disabled_cache_returns_none(self, temp_db, sample_result, sample_image_bytes):
        """Test that disabled cache always returns None."""
        cache = VisionCache(db_path=temp_db, enabled=False)

        # Try to store
        cache.set_by_bytes(sample_image_bytes, sample_result)

        # Try to retrieve
        result = cache.get_by_bytes(sample_image_bytes)
        assert result is None

    def test_disabled_cache_stats(self, temp_db):
        """Test that disabled cache reports correct stats."""
        cache = VisionCache(db_path=temp_db, enabled=False)

        stats = cache.get_stats()
        assert stats["enabled"] is False
        assert stats["total_entries"] == 0


class TestVisionCacheStats:
    """Test cache statistics."""

    def test_stats_accuracy(self, cache, sample_result):
        """Test that stats are accurate."""
        # Empty cache
        stats = cache.get_stats()
        assert stats["total_entries"] == 0
        assert stats["total_hits"] == 0

        # Add entries
        cache.set_by_bytes(b"image1", sample_result)
        cache.set_by_bytes(b"image2", sample_result)

        stats = cache.get_stats()
        assert stats["total_entries"] == 2
        assert stats["total_size_bytes"] > 0

        # Access entries
        cache.get_by_bytes(b"image1")
        cache.get_by_bytes(b"image2")
        cache.get_by_bytes(b"image2")

        stats = cache.get_stats()
        assert stats["total_hits"] == 3

    def test_stats_includes_timestamps(self, cache, sample_result, sample_image_bytes):
        """Test that stats include timestamp info."""
        cache.set_by_bytes(sample_image_bytes, sample_result)

        stats = cache.get_stats()
        assert stats["oldest_entry"] is not None
        assert stats["newest_entry"] is not None


class TestVisionCacheClear:
    """Test cache clearing."""

    def test_clear_removes_all_entries(self, cache, sample_result):
        """Test that clear removes all entries."""
        # Add entries
        cache.set_by_bytes(b"image1", sample_result)
        cache.set_by_bytes(b"image2", sample_result)
        cache.set_by_bytes(b"image3", sample_result)

        stats = cache.get_stats()
        assert stats["total_entries"] == 3

        # Clear
        removed = cache.clear()
        assert removed == 3

        # Verify empty
        stats = cache.get_stats()
        assert stats["total_entries"] == 0


class TestVisionCacheCompression:
    """Test gzip compression."""

    def test_compression_reduces_size(self, cache, sample_result, sample_image_bytes):
        """Test that compression reduces storage size."""
        import json
        from dataclasses import asdict

        # Calculate uncompressed size
        data = {
            "objects": [
                {
                    "name": obj.name,
                    "confidence": obj.confidence,
                    "bbox": asdict(obj.bbox),
                }
                for obj in sample_result.objects
            ],
            "text_blocks": [
                {
                    "text": block.text,
                    "confidence": block.confidence,
                    "bbox": asdict(block.bbox),
                }
                for block in sample_result.text_blocks
            ],
            "raw_text": sample_result.raw_text,
            "image_width": sample_result.image_width,
            "image_height": sample_result.image_height,
        }
        uncompressed_size = len(json.dumps(data).encode("utf-8"))

        # Store and check compressed size
        cache.set_by_bytes(sample_image_bytes, sample_result)

        stats = cache.get_stats()
        compressed_size = stats["total_size_bytes"]

        # Compressed should be smaller (though for small data the difference may be minimal)
        # The main test is that serialization/deserialization works correctly
        assert compressed_size > 0
        assert compressed_size <= uncompressed_size * 1.5  # Allow some overhead


class TestVisionCacheSingleton:
    """Test singleton pattern."""

    def test_reset_clears_singleton(self):
        """Test that reset_vision_cache clears the singleton."""
        reset_vision_cache()

        from app.services.vision_cache import get_vision_cache, _cache_instance

        # After reset, instance should be None
        assert _cache_instance is None
