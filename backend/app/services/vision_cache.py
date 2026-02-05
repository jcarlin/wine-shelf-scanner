"""
Vision API Response Cache Service.

Caches Vision API responses by image hash to reduce API calls and latency.
Provides ~2s savings on cache hit (typical Vision API call is 2-2.5s).
"""

import gzip
import hashlib
import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .vision import BoundingBox, DetectedObject, TextBlock, VisionResult

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Statistics for the vision cache."""
    total_entries: int
    total_hits: int
    total_size_bytes: int
    oldest_entry: Optional[datetime]
    newest_entry: Optional[datetime]


class VisionCache:
    """
    SQLite-based cache for Vision API responses.

    Caches VisionResult objects by SHA256 hash of image bytes.
    Uses gzip compression to reduce storage (~100KB -> ~10-15KB).

    Features:
    - TTL-based expiration
    - Size-based LRU eviction
    - Hit counting for analytics
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        enabled: bool = True,
        ttl_days: int = 7,
        max_size_mb: int = 500,
    ):
        """
        Initialize the vision cache.

        Args:
            db_path: Path to SQLite database. Defaults to data/wines.db
            enabled: Whether caching is enabled
            ttl_days: Time-to-live in days (0 = no expiry)
            max_size_mb: Maximum cache size in MB before LRU eviction
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "wines.db"
        self.db_path = db_path
        self.enabled = enabled
        self.ttl_days = ttl_days
        self.max_size_bytes = max_size_mb * 1024 * 1024

        # Table is created by Alembic migration 003

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _hash_image(self, image_bytes: bytes) -> str:
        """Compute SHA256 hash of image bytes."""
        return hashlib.sha256(image_bytes).hexdigest()

    def _serialize_result(self, result: VisionResult) -> bytes:
        """Serialize VisionResult to gzip-compressed JSON."""
        data = {
            "objects": [
                {
                    "name": obj.name,
                    "confidence": obj.confidence,
                    "bbox": asdict(obj.bbox),
                }
                for obj in result.objects
            ],
            "text_blocks": [
                {
                    "text": block.text,
                    "confidence": block.confidence,
                    "bbox": asdict(block.bbox),
                }
                for block in result.text_blocks
            ],
            "raw_text": result.raw_text,
            "image_width": result.image_width,
            "image_height": result.image_height,
        }
        json_bytes = json.dumps(data).encode("utf-8")
        return gzip.compress(json_bytes)

    def _deserialize_result(self, compressed_data: bytes) -> VisionResult:
        """Deserialize gzip-compressed JSON to VisionResult."""
        json_bytes = gzip.decompress(compressed_data)
        data = json.loads(json_bytes.decode("utf-8"))

        objects = [
            DetectedObject(
                name=obj["name"],
                confidence=obj["confidence"],
                bbox=BoundingBox(**obj["bbox"]),
            )
            for obj in data.get("objects", [])
        ]

        text_blocks = [
            TextBlock(
                text=block["text"],
                confidence=block["confidence"],
                bbox=BoundingBox(**block["bbox"]),
            )
            for block in data.get("text_blocks", [])
        ]

        return VisionResult(
            objects=objects,
            text_blocks=text_blocks,
            raw_text=data.get("raw_text", ""),
            image_width=data.get("image_width", 0),
            image_height=data.get("image_height", 0),
        )

    def get_by_bytes(self, image_bytes: bytes) -> Optional[VisionResult]:
        """
        Get cached Vision API result for an image.

        Args:
            image_bytes: Raw image bytes

        Returns:
            VisionResult if found and not expired, None otherwise
        """
        if not self.enabled:
            return None

        image_hash = self._hash_image(image_bytes)

        conn = self._get_connection()
        try:
            # Check for cached result
            cursor = conn.execute(
                """
                SELECT response_data, ttl_expires_at
                FROM vision_cache
                WHERE image_hash = ?
                """,
                (image_hash,)
            )
            row = cursor.fetchone()

            if row is None:
                logger.debug(f"Vision cache MISS: {image_hash[:12]}...")
                return None

            # Check TTL
            if row["ttl_expires_at"]:
                expires = datetime.fromisoformat(row["ttl_expires_at"])
                if datetime.now() > expires:
                    # Expired - delete and return None
                    conn.execute(
                        "DELETE FROM vision_cache WHERE image_hash = ?",
                        (image_hash,)
                    )
                    conn.commit()
                    logger.debug(f"Vision cache EXPIRED: {image_hash[:12]}...")
                    return None

            # Update hit count and last_accessed
            conn.execute(
                """
                UPDATE vision_cache
                SET hit_count = hit_count + 1,
                    last_accessed_at = CURRENT_TIMESTAMP
                WHERE image_hash = ?
                """,
                (image_hash,)
            )
            conn.commit()

            # Deserialize and return
            result = self._deserialize_result(row["response_data"])
            logger.info(f"Vision cache HIT: {image_hash[:12]}... ({len(result.objects)} objects)")
            return result

        except Exception as e:
            logger.warning(f"Vision cache get error: {e}")
            return None
        finally:
            conn.close()

    def set_by_bytes(self, image_bytes: bytes, result: VisionResult) -> None:
        """
        Cache a Vision API result.

        Args:
            image_bytes: Raw image bytes (used for hash key)
            result: VisionResult to cache
        """
        if not self.enabled:
            return

        image_hash = self._hash_image(image_bytes)
        compressed_data = self._serialize_result(result)

        # Calculate TTL expiration
        ttl_expires = None
        if self.ttl_days > 0:
            ttl_expires = datetime.now() + timedelta(days=self.ttl_days)

        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO vision_cache
                    (image_hash, response_data, image_size_bytes, response_size_bytes, ttl_expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(image_hash) DO UPDATE SET
                    response_data = excluded.response_data,
                    response_size_bytes = excluded.response_size_bytes,
                    last_accessed_at = CURRENT_TIMESTAMP,
                    ttl_expires_at = excluded.ttl_expires_at
                """,
                (image_hash, compressed_data, len(image_bytes), len(compressed_data), ttl_expires)
            )
            conn.commit()
            logger.debug(
                f"Vision cache SET: {image_hash[:12]}... "
                f"({len(image_bytes)} -> {len(compressed_data)} bytes)"
            )

            # Check if we need to evict old entries
            self._maybe_evict(conn)

        except Exception as e:
            logger.warning(f"Vision cache set error: {e}")
        finally:
            conn.close()

    def _maybe_evict(self, conn: sqlite3.Connection) -> None:
        """Evict oldest entries if cache exceeds max size."""
        cursor = conn.execute(
            "SELECT SUM(response_size_bytes) as total_size FROM vision_cache"
        )
        row = cursor.fetchone()
        total_size = row["total_size"] or 0

        if total_size <= self.max_size_bytes:
            return

        # Evict oldest entries until under limit
        target_size = int(self.max_size_bytes * 0.8)  # Evict to 80% capacity
        bytes_to_free = total_size - target_size

        cursor = conn.execute(
            """
            SELECT id, response_size_bytes
            FROM vision_cache
            ORDER BY last_accessed_at ASC
            """
        )

        ids_to_delete = []
        freed = 0
        for row in cursor:
            ids_to_delete.append(row["id"])
            freed += row["response_size_bytes"]
            if freed >= bytes_to_free:
                break

        if ids_to_delete:
            placeholders = ",".join("?" * len(ids_to_delete))
            conn.execute(
                f"DELETE FROM vision_cache WHERE id IN ({placeholders})",
                ids_to_delete
            )
            conn.commit()
            logger.info(f"Vision cache evicted {len(ids_to_delete)} entries, freed {freed} bytes")

    def cleanup(self) -> int:
        """
        Remove expired entries.

        Returns:
            Number of entries removed
        """
        if not self.enabled:
            return 0

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                DELETE FROM vision_cache
                WHERE ttl_expires_at IS NOT NULL
                AND ttl_expires_at < CURRENT_TIMESTAMP
                """
            )
            conn.commit()
            removed = cursor.rowcount
            if removed > 0:
                logger.info(f"Vision cache cleanup: removed {removed} expired entries")
            return removed
        finally:
            conn.close()

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache metrics
        """
        if not self.enabled:
            return {
                "enabled": False,
                "total_entries": 0,
                "total_hits": 0,
                "total_size_bytes": 0,
                "total_size_mb": 0.0,
                "max_size_mb": self.max_size_bytes / (1024 * 1024),
                "ttl_days": self.ttl_days,
            }

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total_entries,
                    COALESCE(SUM(hit_count), 0) as total_hits,
                    COALESCE(SUM(response_size_bytes), 0) as total_size_bytes,
                    MIN(created_at) as oldest_entry,
                    MAX(created_at) as newest_entry
                FROM vision_cache
                """
            )
            row = cursor.fetchone()

            total_size_bytes = row["total_size_bytes"] or 0

            return {
                "enabled": True,
                "total_entries": row["total_entries"] or 0,
                "total_hits": row["total_hits"] or 0,
                "total_size_bytes": total_size_bytes,
                "total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
                "max_size_mb": self.max_size_bytes / (1024 * 1024),
                "ttl_days": self.ttl_days,
                "oldest_entry": row["oldest_entry"],
                "newest_entry": row["newest_entry"],
            }
        finally:
            conn.close()

    def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries removed
        """
        if not self.enabled:
            return 0

        conn = self._get_connection()
        try:
            cursor = conn.execute("DELETE FROM vision_cache")
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()


# Singleton instance
_cache_instance: Optional[VisionCache] = None


def get_vision_cache() -> VisionCache:
    """Get the singleton vision cache instance."""
    global _cache_instance
    if _cache_instance is None:
        from ..config import Config
        _cache_instance = VisionCache(
            enabled=Config.vision_cache_enabled(),
            ttl_days=Config.vision_cache_ttl_days(),
            max_size_mb=Config.vision_cache_max_size_mb(),
        )
    return _cache_instance


def reset_vision_cache() -> None:
    """Reset the singleton instance (for testing)."""
    global _cache_instance
    _cache_instance = None
