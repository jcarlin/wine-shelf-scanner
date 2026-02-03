"""
LLM Rating Cache Service.

Caches LLM-estimated wine ratings to reduce API calls for repeated requests.
Also tracks hit counts for promoting popular wines to the main database.
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CachedRating:
    """A cached LLM-estimated rating."""
    wine_name: str
    estimated_rating: float
    confidence: float
    llm_provider: str
    hit_count: int
    created_at: datetime
    last_accessed_at: datetime
    # Extended metadata from LLM
    wine_type: Optional[str] = None
    region: Optional[str] = None
    varietal: Optional[str] = None
    brand: Optional[str] = None


class LLMRatingCache:
    """
    Cache for LLM-estimated wine ratings.

    Provides:
    - Fast lookup of previously estimated ratings
    - Hit counting for popular wines
    - Promotion candidates (wines requested 5+ times)
    """

    # Minimum hits before a wine is considered for DB promotion
    PROMOTION_THRESHOLD = 5

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize cache.

        Args:
            db_path: Path to SQLite database. Defaults to data/wines.db
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "wines.db"
        self.db_path = db_path
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        """Ensure the cache table exists with all columns."""
        conn = self._get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_ratings_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wine_name TEXT NOT NULL UNIQUE,
                    estimated_rating REAL NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.7,
                    llm_provider TEXT NOT NULL,
                    hit_count INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    wine_type TEXT,
                    region TEXT,
                    varietal TEXT,
                    brand TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_llm_ratings_cache_wine_name
                ON llm_ratings_cache(LOWER(wine_name))
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_llm_ratings_cache_hit_count
                ON llm_ratings_cache(hit_count DESC)
            """)

            # Add columns if they don't exist (for existing databases)
            self._add_column_if_missing(conn, "wine_type", "TEXT")
            self._add_column_if_missing(conn, "region", "TEXT")
            self._add_column_if_missing(conn, "varietal", "TEXT")
            self._add_column_if_missing(conn, "brand", "TEXT")

            conn.commit()
        finally:
            conn.close()

    def _add_column_if_missing(
        self,
        conn: sqlite3.Connection,
        column_name: str,
        column_type: str
    ) -> None:
        """Add column to llm_ratings_cache if it doesn't exist."""
        cursor = conn.execute("PRAGMA table_info(llm_ratings_cache)")
        columns = [row[1] for row in cursor.fetchall()]
        if column_name not in columns:
            conn.execute(
                f"ALTER TABLE llm_ratings_cache ADD COLUMN {column_name} {column_type}"
            )

    def _normalize_name(self, wine_name: str) -> str:
        """Normalize wine name for consistent lookups."""
        return wine_name.strip().lower()

    def get(self, wine_name: str, increment_hit: bool = True) -> Optional[CachedRating]:
        """
        Get cached rating for a wine.

        By default increments hit count and updates last_accessed_at.

        Args:
            wine_name: Wine name to look up
            increment_hit: If True, increment hit count (default: True)

        Returns:
            CachedRating if found, None otherwise
        """
        normalized = self._normalize_name(wine_name)

        conn = self._get_connection()
        try:
            # Get existing rating
            cursor = conn.execute(
                """
                SELECT wine_name, estimated_rating, confidence, llm_provider,
                       hit_count, created_at, last_accessed_at,
                       wine_type, region, varietal, brand
                FROM llm_ratings_cache
                WHERE LOWER(wine_name) = ?
                """,
                (normalized,)
            )
            row = cursor.fetchone()

            if row is None:
                return None

            hit_count = row["hit_count"]

            # Increment hit count and update last_accessed
            if increment_hit:
                conn.execute(
                    """
                    UPDATE llm_ratings_cache
                    SET hit_count = hit_count + 1,
                        last_accessed_at = CURRENT_TIMESTAMP
                    WHERE LOWER(wine_name) = ?
                    """,
                    (normalized,)
                )
                conn.commit()
                hit_count += 1

            return CachedRating(
                wine_name=row["wine_name"],
                estimated_rating=row["estimated_rating"],
                confidence=row["confidence"],
                llm_provider=row["llm_provider"],
                hit_count=hit_count,
                created_at=datetime.fromisoformat(row["created_at"]),
                last_accessed_at=datetime.now(),
                wine_type=row["wine_type"],
                region=row["region"],
                varietal=row["varietal"],
                brand=row["brand"],
            )

        finally:
            conn.close()

    def set(
        self,
        wine_name: str,
        estimated_rating: float,
        confidence: float,
        llm_provider: str,
        wine_type: Optional[str] = None,
        region: Optional[str] = None,
        varietal: Optional[str] = None,
        brand: Optional[str] = None,
    ) -> None:
        """
        Cache an LLM-estimated rating.

        If the wine already exists, updates the rating and provider
        but preserves the hit count.

        Args:
            wine_name: Wine name
            estimated_rating: Estimated rating (1.0-5.0)
            confidence: LLM confidence in estimate (0.0-1.0)
            llm_provider: Provider name ('claude' or 'gemini')
            wine_type: Wine type (Red, White, etc.)
            region: Wine region
            varietal: Grape variety
            brand: Producer/winery name
        """
        # Validate rating
        estimated_rating = max(1.0, min(5.0, estimated_rating))
        confidence = max(0.0, min(1.0, confidence))

        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO llm_ratings_cache
                    (wine_name, estimated_rating, confidence, llm_provider,
                     wine_type, region, varietal, brand)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(wine_name) DO UPDATE SET
                    estimated_rating = excluded.estimated_rating,
                    confidence = excluded.confidence,
                    llm_provider = excluded.llm_provider,
                    wine_type = excluded.wine_type,
                    region = excluded.region,
                    varietal = excluded.varietal,
                    brand = excluded.brand,
                    last_accessed_at = CURRENT_TIMESTAMP
                """,
                (wine_name.strip(), estimated_rating, confidence, llm_provider,
                 wine_type, region, varietal, brand)
            )
            conn.commit()
            logger.debug(f"Cached LLM rating: {wine_name} = {estimated_rating:.1f}")

        finally:
            conn.close()

    def get_promotion_candidates(self, min_hits: int = None) -> list[CachedRating]:
        """
        Get wines that have been requested frequently.

        These are candidates for promotion to the main wines table.

        Args:
            min_hits: Minimum hit count (default: PROMOTION_THRESHOLD)

        Returns:
            List of CachedRating sorted by hit_count descending
        """
        if min_hits is None:
            min_hits = self.PROMOTION_THRESHOLD

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT wine_name, estimated_rating, confidence, llm_provider,
                       hit_count, created_at, last_accessed_at,
                       wine_type, region, varietal, brand
                FROM llm_ratings_cache
                WHERE hit_count >= ?
                ORDER BY hit_count DESC
                """,
                (min_hits,)
            )

            results = []
            for row in cursor:
                results.append(CachedRating(
                    wine_name=row["wine_name"],
                    estimated_rating=row["estimated_rating"],
                    confidence=row["confidence"],
                    llm_provider=row["llm_provider"],
                    hit_count=row["hit_count"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    last_accessed_at=datetime.fromisoformat(row["last_accessed_at"]),
                    wine_type=row["wine_type"],
                    region=row["region"],
                    varietal=row["varietal"],
                    brand=row["brand"],
                ))

            return results

        finally:
            conn.close()

    def delete(self, wine_name: str) -> bool:
        """
        Delete a cached rating (e.g., after promoting to main DB).

        Args:
            wine_name: Wine name to delete

        Returns:
            True if deleted, False if not found
        """
        normalized = self._normalize_name(wine_name)

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM llm_ratings_cache WHERE LOWER(wine_name) = ?",
                (normalized,)
            )
            conn.commit()
            return cursor.rowcount > 0

        finally:
            conn.close()

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with total_entries, total_hits, promotion_candidates
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total_entries,
                    SUM(hit_count) as total_hits,
                    SUM(CASE WHEN hit_count >= ? THEN 1 ELSE 0 END) as promotion_candidates
                FROM llm_ratings_cache
                """,
                (self.PROMOTION_THRESHOLD,)
            )
            row = cursor.fetchone()

            return {
                "total_entries": row["total_entries"] or 0,
                "total_hits": row["total_hits"] or 0,
                "promotion_candidates": row["promotion_candidates"] or 0
            }

        finally:
            conn.close()


# Singleton instance
_cache_instance: Optional[LLMRatingCache] = None


def get_llm_rating_cache() -> LLMRatingCache:
    """Get the singleton LLM rating cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = LLMRatingCache()
    return _cache_instance
