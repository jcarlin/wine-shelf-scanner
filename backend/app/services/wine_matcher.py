"""
Wine name matching against ratings database.

Uses exact-match-only architecture for optimal performance:
- SQLite indexed lookups: ~0.3ms per query
- No in-memory indexes needed
- Instant startup

Supports both JSON and SQLite backends:
- JSON: Legacy mode (ratings.json)
- SQLite: New mode with WineRepository (recommended)
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .wine_repository import WineRepository


@dataclass
class FuzzyScores:
    """Individual scores from matching (simplified for exact-match mode)."""
    ratio: float
    partial_ratio: float
    token_sort_ratio: float
    phonetic_bonus: float
    weighted_score: float


@dataclass
class WineMatch:
    """A matched wine from the database."""
    canonical_name: str
    rating: float
    confidence: float  # Match confidence (0-1)
    source: str


@dataclass
class WineMatchWithScores:
    """A matched wine with detailed matching scores."""
    canonical_name: str
    rating: float
    confidence: float
    source: str
    scores: FuzzyScores


class WineMatcher:
    """
    Exact-match wine matcher for wine names.

    Uses direct SQLite indexed lookups for optimal performance:
    - Exact name match (confidence 1.0)
    - FTS5 prefix match for OCR fragments (confidence 0.85)
    """

    def __init__(
        self,
        database_path: Optional[str] = None,
        repository: Optional["WineRepository"] = None,
        use_sqlite: bool = False,
    ):
        """
        Initialize matcher with ratings database.

        Args:
            database_path: Path to ratings JSON file (legacy mode).
            repository: WineRepository instance for SQLite mode.
            use_sqlite: If True and no repository, create one automatically.
        """
        self._repository = repository
        self._json_database: Optional[dict] = None
        self._name_to_wine: dict[str, dict] = {}

        if repository is not None:
            # Use provided repository - no loading needed
            self._repository = repository
        elif use_sqlite:
            # Create repository automatically - no loading needed
            from .wine_repository import WineRepository
            self._repository = WineRepository()
        else:
            # Legacy JSON mode - load into memory
            if database_path is None:
                database_path = Path(__file__).parent.parent / "data" / "ratings.json"
            self._json_database = self._load_database(database_path)
            self._build_json_index()

    def _load_database(self, path: Path) -> dict:
        """Load ratings database from JSON file."""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"wines": []}

    def _build_json_index(self) -> None:
        """Build simple name lookup index for JSON mode only."""
        if self._json_database is None:
            return

        for wine in self._json_database.get("wines", []):
            canonical = wine["canonical_name"].lower()
            self._name_to_wine[canonical] = wine

            # Index aliases
            for alias in wine.get("aliases", []):
                alias_lower = alias.lower()
                self._name_to_wine[alias_lower] = wine

            # Index winery name
            winery = wine.get("winery")
            if winery:
                winery_lower = winery.lower()
                if winery_lower not in self._name_to_wine:
                    self._name_to_wine[winery_lower] = wine

    def match(self, query: str) -> Optional[WineMatch]:
        """
        Find wine by exact name match (case-insensitive).

        Args:
            query: Normalized wine name from OCR

        Returns:
            WineMatch if found, None otherwise
        """
        if not query:
            return None

        query_lower = query.lower().strip()

        # Skip very short queries
        if len(query_lower) < 3:
            return None

        # Use SQLite repository if available
        if self._repository is not None:
            return self._match_sqlite(query_lower)

        # Fall back to JSON lookup
        return self._match_json(query_lower)

    def _match_sqlite(self, query_lower: str) -> Optional[WineMatch]:
        """Match using SQLite repository."""
        # Step 1: Exact canonical name or alias match
        result = self._repository.find_by_name(query_lower)
        if result:
            return WineMatch(
                canonical_name=result.canonical_name,
                rating=result.rating,
                confidence=1.0,
                source="database"
            )

        # Step 2: Try FTS5 for prefix matches (handles OCR fragments)
        results = self._repository.search_fts(query_lower, limit=1)
        if results:
            return WineMatch(
                canonical_name=results[0].canonical_name,
                rating=results[0].rating,
                confidence=0.85,  # Slightly lower for FTS match
                source="database"
            )

        return None

    def _match_json(self, query_lower: str) -> Optional[WineMatch]:
        """Match using in-memory JSON index."""
        if query_lower in self._name_to_wine:
            wine = self._name_to_wine[query_lower]
            return WineMatch(
                canonical_name=wine["canonical_name"],
                rating=wine["rating"],
                confidence=1.0,
                source=wine.get("source", "unknown")
            )
        return None

    def match_with_scores(self, query: str) -> Optional[WineMatchWithScores]:
        """
        Find matching wine with detailed scores (for debug mode).

        In exact-match mode, scores are simplified:
        - Exact match: all scores = 1.0
        - FTS match: all scores = 0.85
        """
        match = self.match(query)
        if match is None:
            return None

        # Create simplified scores based on confidence
        score = match.confidence
        return WineMatchWithScores(
            canonical_name=match.canonical_name,
            rating=match.rating,
            confidence=match.confidence,
            source=match.source,
            scores=FuzzyScores(
                ratio=score,
                partial_ratio=score,
                token_sort_ratio=score,
                phonetic_bonus=0.0,
                weighted_score=score
            )
        )

    def match_many(self, queries: list[str]) -> list[Optional[WineMatch]]:
        """Match multiple queries."""
        return [self.match(q) for q in queries]

    def get_all_wines(self) -> list[dict]:
        """Return all wines in the database."""
        if self._repository is not None:
            return self._repository.get_all_as_dict()
        if self._json_database is not None:
            return self._json_database.get("wines", [])
        return []

    def reload(self):
        """Reload database (no-op for SQLite, rebuilds index for JSON)."""
        if self._json_database is not None:
            self._build_json_index()
        # SQLite mode needs no reload - queries go directly to DB

    def wine_count(self) -> int:
        """Return total number of wines in database."""
        if self._repository is not None:
            return self._repository.count()
        if self._json_database is not None:
            return len(self._json_database.get("wines", []))
        return 0

    @property
    def database(self) -> dict:
        """Legacy property for backward compatibility."""
        if self._json_database is not None:
            return self._json_database
        # For SQLite mode, return empty dict - callers should use get_all_wines()
        return {"wines": []}
