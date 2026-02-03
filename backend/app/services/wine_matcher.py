"""
Wine name matching against ratings database.

Uses tiered matching for accuracy:
1. Exact canonical name/alias match (confidence 1.0)
2. FTS5 prefix match (confidence 0.9)
3. Fuzzy match with rapidfuzz (confidence based on score)

Supports both JSON and SQLite backends:
- JSON: Legacy mode (ratings.json)
- SQLite: New mode with WineRepository (recommended)
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from rapidfuzz import fuzz
import jellyfish

from ..config import Config

if TYPE_CHECKING:
    from .wine_repository import WineRepository


# Generic wine terms that should not match by themselves
# These are categories/styles, not actual wine names
GENERIC_WINE_TERMS = {
    # French generic terms
    'bordeaux', 'bourgogne', 'burgundy', 'champagne', 'alsace', 'rhone',
    'côtes', 'cotes', 'grand', 'vin', 'rouge', 'blanc', 'rosé', 'rose',
    'brut', 'sec', 'methode', 'méthode', 'traditionnelle', 'cremant', 'crémant',
    'appellation', 'controlee', 'contrôlée', 'origine', 'protegee', 'superieur',
    'supérieur', 'cuvee', 'cuvée', 'reserve', 'réserve',
    # Italian generic terms
    'prosecco', 'spumante', 'classico', 'riserva', 'superiore',
    # Spanish generic terms
    'cava', 'crianza', 'reserva', 'gran',
}

# LLM-specific patterns that indicate a generic response (more restrictive)
# These are patterns that LLMs tend to return when they can't identify a wine
LLM_GENERIC_PATTERNS = {
    'grand vin', 'grand cru', 'premier cru', 'appellation', 'controlee',
    'methode traditionnelle', 'méthode traditionnelle',
    # Non-wine label boilerplate that LLMs sometimes return
    'este noble vino', 'fue elaborado', 'com uvas', 'de altitude',
    'cuvee speciale', 'cuvée spéciale', 'extra brut',
}


def _is_generic_query(query: str) -> bool:
    """
    Check if a query consists only of generic wine terms.

    Returns True if matching this query would likely produce a false positive.
    """
    query_lower = query.lower()
    words = set(query_lower.split())

    # If all words are generic terms, reject
    non_generic_words = words - GENERIC_WINE_TERMS

    # Also filter out very short words and numbers
    non_generic_words = {w for w in non_generic_words if len(w) >= 3 and not w.isdigit()}

    # If no meaningful non-generic words remain, it's a generic query
    return len(non_generic_words) == 0


def _is_llm_generic_response(wine_name: str) -> bool:
    """
    Check if an LLM-returned wine name looks like a generic fallback.

    More restrictive than _is_generic_query - specifically targets
    patterns that LLMs return when they can't identify a wine.
    """
    name_lower = wine_name.lower()

    # Check for specific generic patterns
    for pattern in LLM_GENERIC_PATTERNS:
        if pattern in name_lower:
            return True

    # Also apply general generic check
    return _is_generic_query(wine_name)


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
    Tiered wine matcher for wine names.

    Uses multiple strategies for optimal accuracy:
    1. Exact name match (confidence 1.0)
    2. FTS5 prefix match (confidence 0.9)
    3. Fuzzy match with rapidfuzz (confidence based on score)
    """

    def __init__(
        self,
        database_path: Optional[str] = None,
        repository: Optional["WineRepository"] = None,
        use_sqlite: Optional[bool] = None,
    ):
        """
        Initialize matcher with ratings database.

        Args:
            database_path: Path to ratings JSON file (legacy mode).
            repository: WineRepository instance for SQLite mode.
            use_sqlite: If True and no repository, create one automatically.
                       Defaults to Config.use_sqlite() if not specified.
        """
        # Default to config setting if not specified
        if use_sqlite is None:
            use_sqlite = Config.use_sqlite()
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

        # Skip queries that are only generic wine terms (avoid false positives)
        if _is_generic_query(query_lower):
            return None

        # Use SQLite repository if available
        if self._repository is not None:
            return self._match_sqlite(query_lower)

        # Fall back to JSON lookup
        return self._match_json(query_lower)

    def _match_sqlite(self, query_lower: str) -> Optional[WineMatch]:
        """Match using SQLite repository with tiered approach."""
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
        fts_results = self._repository.search_fts(query_lower, limit=5)
        if fts_results:
            # Score FTS results with fuzzy matching to pick best
            best_match = None
            best_score = 0.0
            for fts_result in fts_results:
                score = self._compute_fuzzy_score(query_lower, fts_result.canonical_name.lower())
                if score > best_score:
                    best_score = score
                    best_match = fts_result

            if best_match and best_score >= Config.MIN_SIMILARITY:
                return WineMatch(
                    canonical_name=best_match.canonical_name,
                    rating=best_match.rating,
                    confidence=min(0.95, best_score),  # Cap at 0.95 for FTS match
                    source="database"
                )

        # Step 3: Fuzzy match against database candidates
        return self._fuzzy_match_sqlite(query_lower)

    def _compute_fuzzy_score(self, query: str, candidate: str) -> float:
        """
        Compute weighted fuzzy score using multiple algorithms.

        Uses rapidfuzz for accuracy with configurable weights.
        """
        # Multi-algorithm scoring
        ratio = fuzz.ratio(query, candidate) / 100.0
        partial_ratio = fuzz.partial_ratio(query, candidate) / 100.0
        token_sort = fuzz.token_sort_ratio(query, candidate) / 100.0

        # Weighted combination
        weighted = (
            Config.WEIGHT_RATIO * ratio +
            Config.WEIGHT_PARTIAL * partial_ratio +
            Config.WEIGHT_TOKEN_SORT * token_sort
        )

        # Phonetic bonus if sounds similar
        try:
            query_metaphone = jellyfish.metaphone(query[:20])  # Limit for performance
            candidate_metaphone = jellyfish.metaphone(candidate[:20])
            if query_metaphone and candidate_metaphone:
                if query_metaphone == candidate_metaphone:
                    weighted += Config.PHONETIC_BONUS
                elif query_metaphone[:3] == candidate_metaphone[:3]:
                    weighted += Config.PHONETIC_BONUS / 2
        except Exception:
            pass  # Skip phonetic bonus on error

        return min(1.0, weighted)

    def _fuzzy_match_sqlite(self, query_lower: str) -> Optional[WineMatch]:
        """
        Fuzzy match against database using rapidfuzz.

        Performance-optimized approach:
        1. Use FTS5 OR query to find broader set of candidates
        2. Score only those candidates with fuzzy matching
        3. Skip full database scan (too slow for 192K wines)
        """
        # Try broader FTS5 search first (any word match, not all)
        conn = self._repository._get_connection()
        cursor = conn.cursor()

        # Build OR query: "big smooth zin" -> "big" OR "smooth" OR "zin"
        words = [w for w in query_lower.split() if len(w) >= 3]
        if not words:
            return None

        # Use FTS5 OR query for broader matching
        fts_query = ' OR '.join(f'"{w}"*' for w in words[:5])  # Limit words
        try:
            cursor.execute("""
                SELECT w.id, w.canonical_name, w.rating
                FROM wines w
                JOIN wine_fts ON w.id = wine_fts.rowid
                WHERE wine_fts MATCH ?
                ORDER BY rank
                LIMIT 50
            """, (fts_query,))

            candidates = [(row[1], row[0], row[2]) for row in cursor.fetchall()]
        except Exception:
            # FTS query failed, return None
            return None

        if not candidates:
            return None

        # Score candidates with full fuzzy algorithm
        best_match = None
        best_score = 0.0

        for name, wine_id, rating in candidates:
            score = self._compute_fuzzy_score(query_lower, name.lower())
            if score > best_score:
                best_score = score
                best_match = (name, wine_id, rating)

        if best_match and best_score >= Config.FUZZY_CONFIDENCE_THRESHOLD:
            name, wine_id, rating = best_match

            # Avoid matching to wines that are mostly generic terms
            # (e.g., matching "Bordeaux Rouge" to a wine named "Bordeaux Rouge Michel Lynch")
            if _is_generic_query(name):
                return None

            return WineMatch(
                canonical_name=name,
                rating=rating,
                confidence=best_score,
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
