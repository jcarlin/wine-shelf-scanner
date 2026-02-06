"""
Wine database repository with SQLite backend.

Provides thread-safe access to wine database with:
- Connection pooling
- LRU caching for frequent queries
- FTS5 full-text search
"""

import sqlite3
import threading
from dataclasses import dataclass
from typing import Optional
import json

from app.db import BaseRepository


@dataclass
class WineRecord:
    """A wine record from the database."""
    id: int
    canonical_name: str
    rating: float
    wine_type: Optional[str] = None
    region: Optional[str] = None
    winery: Optional[str] = None
    country: Optional[str] = None
    varietal: Optional[str] = None
    description: Optional[str] = None
    aliases: list[str] = None

    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []


@dataclass
class WineReview:
    """A wine review from the database."""
    id: int
    source_name: str
    user_id: Optional[str] = None
    rating: Optional[float] = None
    review_text: Optional[str] = None
    review_date: Optional[str] = None
    vintage: Optional[str] = None


class WineRepository(BaseRepository):
    """
    Thread-safe SQLite repository for wine data.

    Features:
    - Connection pooling per thread
    - LRU cache for name lookups
    - FTS5 search support
    - Bulk operations for ingestion
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize repository.

        Args:
            db_path: Path to SQLite database. Defaults to Config.database_path()
        """
        super().__init__(db_path, use_wal=True)
        self._schema_initialized = False
        self._cache_lock = threading.Lock()

        # Instance-level cache (not shared across instances)
        self._wine_cache: dict[str, WineRecord] = {}
        self._CACHE_SIZE = 5000

        # Initialize schema
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema via Alembic migrations."""
        if self._schema_initialized:
            return

        from app.db import ensure_schema
        ensure_schema(self.db_path)
        self._schema_initialized = True

    def find_by_name(self, name: str) -> Optional[WineRecord]:
        """
        Find wine by exact name (case-insensitive).

        Checks both canonical names and aliases.
        """
        # Check cache first
        cached = self._get_cached_wine(name.lower())
        if cached is not None:
            return cached

        conn = self._get_connection()
        cursor = conn.cursor()

        # Try canonical name
        cursor.execute("""
            SELECT id, canonical_name, rating, wine_type, region, winery, country, varietal, description
            FROM wines
            WHERE LOWER(canonical_name) = LOWER(?)
        """, (name,))

        row = cursor.fetchone()
        if row:
            record = self._row_to_record(row, cursor)
            self._cache_wine(record)
            return record

        # Try alias
        cursor.execute("""
            SELECT w.id, w.canonical_name, w.rating, w.wine_type, w.region, w.winery, w.country, w.varietal, w.description
            FROM wines w
            JOIN wine_aliases a ON w.id = a.wine_id
            WHERE LOWER(a.alias_name) = LOWER(?)
        """, (name,))

        row = cursor.fetchone()
        if row:
            record = self._row_to_record(row, cursor)
            self._cache_wine(record)
            return record

        return None

    def search_fts(self, query: str, limit: int = 10) -> list[WineRecord]:
        """
        Full-text search using FTS5 with prefix matching.

        Args:
            query: Search query
            limit: Maximum results to return
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Build prefix query: "caymus cabernet" -> "caymus* cabernet*"
        # This matches wines starting with these words
        words = query.split()
        safe_words = [w.replace('"', '""') for w in words if w]
        fts_query = ' '.join(f'"{w}"*' for w in safe_words)

        if not fts_query:
            return []

        cursor.execute("""
            SELECT w.id, w.canonical_name, w.rating, w.wine_type, w.region, w.winery, w.country, w.varietal, w.description
            FROM wines w
            JOIN wine_fts ON w.id = wine_fts.rowid
            WHERE wine_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (fts_query, limit))

        results = []
        for row in cursor.fetchall():
            record = self._row_to_record_simple(row)
            results.append(record)

        return results

    def search_fts_or(self, query: str, limit: int = 50) -> list[WineRecord]:
        """
        Full-text search using FTS5 with OR matching.

        Unlike search_fts which requires all words to match (AND),
        this returns wines matching ANY of the query words (OR).
        Useful for fuzzy matching candidates.

        Args:
            query: Search query (words at least 3 chars are used)
            limit: Maximum results to return

        Returns:
            List of WineRecord matching any query word
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Filter to words at least 3 chars
        words = [w.replace('"', '""') for w in query.lower().split() if len(w) >= 3]
        if not words:
            return []

        # Build OR query: "big smooth zin" -> "big"* OR "smooth"* OR "zin"*
        fts_query = ' OR '.join(f'"{w}"*' for w in words[:5])  # Limit words

        try:
            cursor.execute("""
                SELECT w.id, w.canonical_name, w.rating, w.wine_type, w.region, w.winery, w.country, w.varietal, w.description
                FROM wines w
                JOIN wine_fts ON w.id = wine_fts.rowid
                WHERE wine_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, limit))

            return [self._row_to_record_simple(row) for row in cursor.fetchall()]
        except Exception:
            return []

    def _row_to_record_simple(self, row: sqlite3.Row) -> WineRecord:
        """Convert database row to WineRecord without fetching aliases."""
        return WineRecord(
            id=row['id'],
            canonical_name=row['canonical_name'],
            rating=row['rating'],
            wine_type=row['wine_type'],
            region=row['region'],
            winery=row['winery'],
            country=row['country'],
            varietal=row['varietal'],
            description=row['description'],
            aliases=[],  # Skip aliases for FTS results (performance)
        )

    def get_all(self) -> list[WineRecord]:
        """Get all wines from database with aliases in single query."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Single query with GROUP_CONCAT to avoid N+1 problem
        cursor.execute("""
            SELECT w.id, w.canonical_name, w.rating, w.wine_type, w.region,
                   w.winery, w.country, w.varietal, w.description,
                   GROUP_CONCAT(a.alias_name, '|') as aliases
            FROM wines w
            LEFT JOIN wine_aliases a ON w.id = a.wine_id
            GROUP BY w.id
            ORDER BY w.canonical_name
        """)

        results = []
        for row in cursor.fetchall():
            aliases = row['aliases'].split('|') if row['aliases'] else []
            results.append(WineRecord(
                id=row['id'],
                canonical_name=row['canonical_name'],
                rating=row['rating'],
                wine_type=row['wine_type'],
                region=row['region'],
                winery=row['winery'],
                country=row['country'],
                varietal=row['varietal'],
                description=row['description'],
                aliases=aliases,
            ))

        return results

    def get_all_as_dict(self) -> list[dict]:
        """Get all wines as dicts with aliases in single query."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Single query with GROUP_CONCAT to avoid N+1 problem
        cursor.execute("""
            SELECT w.id, w.canonical_name, w.rating, w.wine_type, w.region,
                   w.winery, w.country, w.varietal,
                   GROUP_CONCAT(a.alias_name, '|') as aliases
            FROM wines w
            LEFT JOIN wine_aliases a ON w.id = a.wine_id
            GROUP BY w.id
        """)

        results = []
        for row in cursor.fetchall():
            aliases = row['aliases'].split('|') if row['aliases'] else []
            results.append({
                "canonical_name": row['canonical_name'],
                "rating": row['rating'],
                "source": "database",
                "aliases": aliases,
                "wine_type": row['wine_type'],
                "region": row['region'],
                "winery": row['winery'],
                "country": row['country'],
                "varietal": row['varietal'],
            })

        return results

    def add_wine(
        self,
        canonical_name: str,
        rating: float,
        wine_type: Optional[str] = None,
        region: Optional[str] = None,
        winery: Optional[str] = None,
        country: Optional[str] = None,
        varietal: Optional[str] = None,
        aliases: list[str] = None,
        source_name: Optional[str] = None,
        original_rating: Optional[float] = None,
        original_scale: Optional[tuple[float, float]] = None,
    ) -> int:
        """
        Add a wine to the database.

        Returns the wine ID.
        """
        with self._transaction() as cursor:
            cursor.execute("""
                INSERT INTO wines (canonical_name, rating, wine_type, region, winery, country, varietal)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (canonical_name, rating, wine_type, region, winery, country, varietal))

            wine_id = cursor.lastrowid

            # Add aliases
            if aliases:
                for alias in aliases:
                    cursor.execute("""
                        INSERT OR IGNORE INTO wine_aliases (wine_id, alias_name)
                        VALUES (?, ?)
                    """, (wine_id, alias))

            # Add source info
            if source_name and original_rating is not None and original_scale:
                cursor.execute("""
                    INSERT INTO wine_sources (wine_id, source_name, original_rating, original_scale_min, original_scale_max)
                    VALUES (?, ?, ?, ?, ?)
                """, (wine_id, source_name, original_rating, original_scale[0], original_scale[1]))

            # Clear cache for this name
            self._invalidate_cache(canonical_name.lower())

            return wine_id

    def update_wine(
        self,
        wine_id: int,
        rating: Optional[float] = None,
        wine_type: Optional[str] = None,
        region: Optional[str] = None,
        winery: Optional[str] = None,
        country: Optional[str] = None,
        varietal: Optional[str] = None,
    ) -> bool:
        """Update wine fields. Returns True if wine was found and updated."""
        updates = []
        params = []

        if rating is not None:
            updates.append("rating = ?")
            params.append(rating)
        if wine_type is not None:
            updates.append("wine_type = ?")
            params.append(wine_type)
        if region is not None:
            updates.append("region = ?")
            params.append(region)
        if winery is not None:
            updates.append("winery = ?")
            params.append(winery)
        if country is not None:
            updates.append("country = ?")
            params.append(country)
        if varietal is not None:
            updates.append("varietal = ?")
            params.append(varietal)

        if not updates:
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(wine_id)

        with self._transaction() as cursor:
            cursor.execute(f"""
                UPDATE wines
                SET {', '.join(updates)}
                WHERE id = ?
            """, tuple(params))

            return cursor.rowcount > 0

    def add_alias(self, wine_id: int, alias_name: str) -> bool:
        """Add an alias to a wine. Returns True if added."""
        with self._transaction() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO wine_aliases (wine_id, alias_name)
                    VALUES (?, ?)
                """, (wine_id, alias_name))
                return True
            except sqlite3.IntegrityError:
                return False

    def add_source(
        self,
        wine_id: int,
        source_name: str,
        original_rating: float,
        original_scale: tuple[float, float]
    ) -> bool:
        """Add or update source information for a wine."""
        with self._transaction() as cursor:
            cursor.execute("""
                INSERT OR REPLACE INTO wine_sources
                (wine_id, source_name, original_rating, original_scale_min, original_scale_max)
                VALUES (?, ?, ?, ?, ?)
            """, (wine_id, source_name, original_rating, original_scale[0], original_scale[1]))
            return cursor.rowcount > 0

    def find_by_id(self, wine_id: int) -> Optional[WineRecord]:
        """Find wine by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, canonical_name, rating, wine_type, region, winery, country, varietal, description
            FROM wines
            WHERE id = ?
        """, (wine_id,))

        row = cursor.fetchone()
        if row:
            return self._row_to_record(row, cursor)
        return None

    def count(self) -> int:
        """Get total wine count."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM wines")
        return cursor.fetchone()[0]

    def exists(self, canonical_name: str) -> bool:
        """Check if wine exists by canonical name."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM wines WHERE LOWER(canonical_name) = LOWER(?) LIMIT 1
        """, (canonical_name,))
        return cursor.fetchone() is not None

    def bulk_insert(self, wines: list[dict], batch_size: int = 1000) -> tuple[int, int]:
        """
        Bulk insert wines for efficient ingestion.

        Args:
            wines: List of wine dicts with canonical_name, rating, etc.
                   Optional keys: aliases (list), sources (dict mapping source_name to
                   tuple of (original_rating, scale_min, scale_max))
            batch_size: Number of records per commit

        Returns:
            Tuple of (inserted_count, skipped_count)
        """
        inserted = 0
        skipped = 0

        conn = self._get_connection()
        cursor = conn.cursor()

        for i, wine in enumerate(wines):
            try:
                cursor.execute("""
                    INSERT INTO wines (canonical_name, rating, wine_type, region, winery, country, varietal, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    wine['canonical_name'],
                    wine['rating'],
                    wine.get('wine_type'),
                    wine.get('region'),
                    wine.get('winery'),
                    wine.get('country'),
                    wine.get('varietal'),
                    wine.get('description'),
                ))
                inserted += 1

                wine_id = cursor.lastrowid

                # Add aliases if present
                for alias in wine.get('aliases', []):
                    cursor.execute("""
                        INSERT OR IGNORE INTO wine_aliases (wine_id, alias_name)
                        VALUES (?, ?)
                    """, (wine_id, alias))

                # Add source information if present
                for source_name, source_data in wine.get('sources', {}).items():
                    original_rating, scale_min, scale_max = source_data
                    cursor.execute("""
                        INSERT OR IGNORE INTO wine_sources
                        (wine_id, source_name, original_rating, original_scale_min, original_scale_max)
                        VALUES (?, ?, ?, ?, ?)
                    """, (wine_id, source_name, original_rating, scale_min, scale_max))

            except sqlite3.IntegrityError:
                skipped += 1

            # Commit in batches
            if (i + 1) % batch_size == 0:
                conn.commit()

        conn.commit()
        self._clear_cache()

        return inserted, skipped

    def _row_to_record(self, row: sqlite3.Row, cursor: sqlite3.Cursor) -> WineRecord:
        """Convert database row to WineRecord."""
        # Fetch aliases
        cursor.execute("""
            SELECT alias_name FROM wine_aliases WHERE wine_id = ?
        """, (row['id'],))
        aliases = [r['alias_name'] for r in cursor.fetchall()]

        return WineRecord(
            id=row['id'],
            canonical_name=row['canonical_name'],
            rating=row['rating'],
            wine_type=row['wine_type'],
            region=row['region'],
            winery=row['winery'],
            country=row['country'],
            varietal=row['varietal'],
            description=row['description'],
            aliases=aliases,
        )

    def get_rating_sources(self, wine_id: int) -> list[dict]:
        """
        Get rating source details for a wine.

        Returns list of dicts with source_name, original_rating, scale_min, scale_max.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT source_name, original_rating, original_scale_min, original_scale_max
            FROM wine_sources
            WHERE wine_id = ?
        """, (wine_id,))
        return [
            {
                "source_name": row["source_name"],
                "original_rating": row["original_rating"],
                "scale_min": row["original_scale_min"],
                "scale_max": row["original_scale_max"],
            }
            for row in cursor.fetchall()
        ]

    def find_by_name_with_id(self, name: str) -> Optional[tuple[WineRecord, int]]:
        """Find wine by name and also return the database ID for source lookups."""
        record = self.find_by_name(name)
        if record:
            return (record, record.id)
        return None

    # Caching methods
    def _get_cached_wine(self, key: str) -> Optional[WineRecord]:
        """Get wine from cache."""
        with self._cache_lock:
            return self._wine_cache.get(key)

    def _cache_wine(self, record: WineRecord):
        """Add wine to cache."""
        with self._cache_lock:
            if len(self._wine_cache) >= self._CACHE_SIZE:
                # Simple eviction: clear half the cache
                keys = list(self._wine_cache.keys())[:self._CACHE_SIZE // 2]
                for k in keys:
                    del self._wine_cache[k]

            self._wine_cache[record.canonical_name.lower()] = record
            for alias in record.aliases:
                self._wine_cache[alias.lower()] = record

    def _invalidate_cache(self, key: str):
        """Remove key from cache."""
        with self._cache_lock:
            self._wine_cache.pop(key, None)

    def _clear_cache(self):
        """Clear entire cache."""
        with self._cache_lock:
            self._wine_cache.clear()

    def get_reviews(self, wine_id: int, limit: int = 10, text_only: bool = True) -> list[WineReview]:
        """
        Get reviews for a wine.

        Args:
            wine_id: Wine database ID
            limit: Maximum reviews to return
            text_only: If True, only return reviews with review_text
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if text_only:
            cursor.execute("""
                SELECT id, source_name, user_id, rating, review_text, review_date, vintage
                FROM wine_reviews
                WHERE wine_id = ? AND review_text IS NOT NULL
                ORDER BY rating DESC
                LIMIT ?
            """, (wine_id, limit))
        else:
            cursor.execute("""
                SELECT id, source_name, user_id, rating, review_text, review_date, vintage
                FROM wine_reviews
                WHERE wine_id = ?
                ORDER BY rating DESC
                LIMIT ?
            """, (wine_id, limit))

        return [
            WineReview(
                id=row['id'],
                source_name=row['source_name'],
                user_id=row['user_id'],
                rating=row['rating'],
                review_text=row['review_text'],
                review_date=row['review_date'],
                vintage=row['vintage'],
            )
            for row in cursor.fetchall()
        ]

    def get_review_stats(self, wine_id: int) -> dict:
        """
        Get review statistics for a wine.

        Returns dict with total_reviews, avg_rating, text_reviews.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as total_reviews,
                AVG(rating) as avg_rating,
                COALESCE(SUM(CASE WHEN review_text IS NOT NULL THEN 1 ELSE 0 END), 0) as text_reviews
            FROM wine_reviews
            WHERE wine_id = ?
        """, (wine_id,))

        row = cursor.fetchone()
        return {
            "total_reviews": row['total_reviews'],
            "avg_rating": round(row['avg_rating'], 2) if row['avg_rating'] else None,
            "text_reviews": row['text_reviews'],
        }

    def migrate_from_json(self, json_path: str) -> tuple[int, int]:
        """
        Migrate data from ratings.json to SQLite.

        Args:
            json_path: Path to ratings.json file

        Returns:
            Tuple of (migrated_count, skipped_count)
        """
        with open(json_path, 'r') as f:
            data = json.load(f)

        wines = []
        for wine in data.get("wines", []):
            wines.append({
                "canonical_name": wine["canonical_name"],
                "rating": wine["rating"],
                "aliases": wine.get("aliases", []),
                "wine_type": wine.get("wine_type"),
                "region": wine.get("region"),
                "winery": wine.get("winery"),
                "country": wine.get("country"),
                "varietal": wine.get("varietal"),
            })

        return self.bulk_insert(wines)
