"""
Wine database repository with SQLite backend.

Provides thread-safe access to wine database with:
- Connection pooling
- LRU caching for frequent queries
- FTS5 full-text search
"""

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional, Iterator
import json


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
    aliases: list[str] = None

    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []


class WineRepository:
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
            db_path: Path to SQLite database. Defaults to data/wines.db
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "wines.db"

        self.db_path = str(db_path)
        self._local = threading.local()
        self._schema_initialized = False
        self._cache_lock = threading.Lock()

        # Instance-level cache (not shared across instances)
        self._wine_cache: dict[str, WineRecord] = {}
        self._CACHE_SIZE = 5000

        # Initialize schema
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")
            # WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode = WAL")
            self._local.connection = conn
        return self._local.connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Cursor]:
        """Context manager for transactions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_schema(self):
        """Initialize database schema if needed."""
        if self._schema_initialized:
            return

        schema_path = Path(__file__).parent.parent / "data" / "schema.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path, 'r') as f:
            schema_sql = f.read()

        conn = self._get_connection()
        conn.executescript(schema_sql)
        conn.commit()
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
            SELECT id, canonical_name, rating, wine_type, region, winery, country, varietal
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
            SELECT w.id, w.canonical_name, w.rating, w.wine_type, w.region, w.winery, w.country, w.varietal
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
            SELECT w.id, w.canonical_name, w.rating, w.wine_type, w.region, w.winery, w.country, w.varietal
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
            aliases=[],  # Skip aliases for FTS results (performance)
        )

    def get_all(self) -> list[WineRecord]:
        """Get all wines from database with aliases in single query."""
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
            SELECT id, canonical_name, rating, wine_type, region, winery, country, varietal
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
                    INSERT INTO wines (canonical_name, rating, wine_type, region, winery, country, varietal)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    wine['canonical_name'],
                    wine['rating'],
                    wine.get('wine_type'),
                    wine.get('region'),
                    wine.get('winery'),
                    wine.get('country'),
                    wine.get('varietal'),
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
            aliases=aliases,
        )

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

    def close(self):
        """Close database connection."""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

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
