"""
Wine name matching against ratings database.

Uses tiered matching for accuracy:
1. Exact canonical name/alias match (confidence 1.0)
2. FTS5 prefix match (confidence 0.9)
3. Fuzzy match with rapidfuzz (confidence based on score)

Supports both JSON and SQLite backends:
- JSON: Legacy mode (ratings.json)
- SQLite: New mode with WineRepository (recommended)

Performance optimization:
- LRU cache for match results (repeated wines on same shelf)
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Optional

from rapidfuzz import fuzz
import jellyfish

from ..config import Config
from ..models.enums import WineSource


# Module-level match cache for performance (thread-safe)
# Caches (query -> WineMatch) to avoid repeated lookups for same wine
_match_cache: dict[str, Optional["WineMatch"]] = {}
_cache_lock = Lock()
_CACHE_MAX_SIZE = 500  # Limit cache size to prevent memory issues

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
    source: WineSource = WineSource.DATABASE
    # Extended metadata from database
    wine_type: Optional[str] = None
    brand: Optional[str] = None  # winery
    region: Optional[str] = None
    varietal: Optional[str] = None
    description: Optional[str] = None
    wine_id: Optional[int] = None


@dataclass
class NearMiss:
    """A candidate that was considered but didn't make the final match."""
    wine_name: str
    score: float
    rejection_reason: str  # "below_threshold", "generic_query"


@dataclass
class FuzzyMatchDebugResult:
    """Result from match_with_debug() with diagnostic info."""
    match: Optional["WineMatchWithScores"]
    near_misses: list[NearMiss]
    fts_candidates_count: int
    rejection_reason: Optional[str]  # "no_fts_candidates", "below_threshold", "generic_query", "query_too_short"


@dataclass
class WineMatchWithScores:
    """A matched wine with detailed matching scores."""
    canonical_name: str
    rating: float
    confidence: float
    source: WineSource
    scores: FuzzyScores
    # Extended metadata from database
    wine_type: Optional[str] = None
    brand: Optional[str] = None
    region: Optional[str] = None
    varietal: Optional[str] = None
    description: Optional[str] = None
    wine_id: Optional[int] = None


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

        Uses module-level cache for performance (repeated wines on same shelf).

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

        # Check cache first (thread-safe)
        with _cache_lock:
            if query_lower in _match_cache:
                return _match_cache[query_lower]

        # Perform actual match
        if self._repository is not None:
            result = self._match_sqlite(query_lower)
        else:
            result = self._match_json(query_lower)

        # Cache result (thread-safe, with size limit)
        with _cache_lock:
            if len(_match_cache) >= _CACHE_MAX_SIZE:
                # Simple eviction: clear half the cache when full
                keys_to_remove = list(_match_cache.keys())[:_CACHE_MAX_SIZE // 2]
                for key in keys_to_remove:
                    del _match_cache[key]
            _match_cache[query_lower] = result

        return result

    def _match_sqlite(self, query_lower: str) -> Optional[WineMatch]:
        """Match using SQLite repository with tiered approach."""
        # Step 1: Exact canonical name or alias match
        result = self._repository.find_by_name(query_lower)
        if result:
            return WineMatch(
                canonical_name=result.canonical_name,
                rating=result.rating,
                confidence=1.0,
                source=WineSource.DATABASE,
                wine_type=result.wine_type,
                brand=result.winery,
                region=result.region,
                varietal=result.varietal,
                description=result.description,
                wine_id=result.id,
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
                    source=WineSource.DATABASE,
                    wine_type=best_match.wine_type,
                    brand=best_match.winery,
                    region=best_match.region,
                    varietal=best_match.varietal,
                    description=best_match.description,
                    wine_id=best_match.id,
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
        # Use repository's OR-based FTS search
        candidates = self._repository.search_fts_or(query_lower, limit=50)
        if not candidates:
            return None

        # Score candidates with full fuzzy algorithm
        best_match = None
        best_score = 0.0

        for wine in candidates:
            score = self._compute_fuzzy_score(query_lower, wine.canonical_name.lower())
            if score > best_score:
                best_score = score
                best_match = wine

        if best_match and best_score >= Config.FUZZY_CONFIDENCE_THRESHOLD:
            # Avoid matching to wines that are mostly generic terms
            # (e.g., matching "Bordeaux Rouge" to a wine named "Bordeaux Rouge Michel Lynch")
            if _is_generic_query(best_match.canonical_name):
                return None

            return WineMatch(
                canonical_name=best_match.canonical_name,
                rating=best_match.rating,
                confidence=best_score,
                source=WineSource.DATABASE,
                wine_type=best_match.wine_type,
                brand=best_match.winery,
                region=best_match.region,
                varietal=best_match.varietal,
                description=best_match.description,
                wine_id=best_match.id,
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
                source=WineSource.DATABASE,  # JSON matches are always from database
                wine_type=wine.get("wine_type"),
                brand=wine.get("winery"),
                region=wine.get("region"),
                varietal=wine.get("varietal"),
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
            ),
            wine_type=match.wine_type,
            brand=match.brand,
            region=match.region,
            varietal=match.varietal,
            description=match.description,
            wine_id=match.wine_id,
        )

    def match_with_debug(self, query: str) -> FuzzyMatchDebugResult:
        """
        Match with full debug diagnostics (near-misses, candidate counts, rejection reasons).

        Only called when debug=True. The normal match/match_with_scores paths are untouched.
        """
        if not query:
            return FuzzyMatchDebugResult(match=None, near_misses=[], fts_candidates_count=0, rejection_reason="query_too_short")

        query_lower = query.lower().strip()

        if len(query_lower) < 3:
            return FuzzyMatchDebugResult(match=None, near_misses=[], fts_candidates_count=0, rejection_reason="query_too_short")

        if _is_generic_query(query_lower):
            return FuzzyMatchDebugResult(match=None, near_misses=[], fts_candidates_count=0, rejection_reason="generic_query")

        if self._repository is None:
            # JSON mode - fall back to simple match
            match = self.match_with_scores(query)
            return FuzzyMatchDebugResult(match=match, near_misses=[], fts_candidates_count=0, rejection_reason=None if match else "no_fts_candidates")

        # Step 1: Exact match
        result = self._repository.find_by_name(query_lower)
        if result:
            scores = FuzzyScores(ratio=1.0, partial_ratio=1.0, token_sort_ratio=1.0, phonetic_bonus=0.0, weighted_score=1.0)
            match = WineMatchWithScores(
                canonical_name=result.canonical_name, rating=result.rating, confidence=1.0,
                source=WineSource.DATABASE, scores=scores, wine_type=result.wine_type,
                brand=result.winery, region=result.region, varietal=result.varietal,
                description=result.description, wine_id=result.id,
            )
            return FuzzyMatchDebugResult(match=match, near_misses=[], fts_candidates_count=0, rejection_reason=None)

        all_near_misses: list[NearMiss] = []

        # Step 2: FTS5 prefix match
        fts_results = self._repository.search_fts(query_lower, limit=5)
        fts_count = len(fts_results)
        if fts_results:
            best_match = None
            best_score = 0.0
            for fts_result in fts_results:
                score = self._compute_fuzzy_score(query_lower, fts_result.canonical_name.lower())
                if score > best_score:
                    best_score = score
                    best_match = fts_result
                if score < Config.MIN_SIMILARITY:
                    all_near_misses.append(NearMiss(wine_name=fts_result.canonical_name, score=score, rejection_reason="below_threshold"))

            if best_match and best_score >= Config.MIN_SIMILARITY:
                # Compute detailed scores for the best match
                ratio = fuzz.ratio(query_lower, best_match.canonical_name.lower()) / 100.0
                partial_ratio = fuzz.partial_ratio(query_lower, best_match.canonical_name.lower()) / 100.0
                token_sort = fuzz.token_sort_ratio(query_lower, best_match.canonical_name.lower()) / 100.0
                scores = FuzzyScores(ratio=ratio, partial_ratio=partial_ratio, token_sort_ratio=token_sort, phonetic_bonus=0.0, weighted_score=best_score)
                match = WineMatchWithScores(
                    canonical_name=best_match.canonical_name, rating=best_match.rating,
                    confidence=min(0.95, best_score), source=WineSource.DATABASE, scores=scores,
                    wine_type=best_match.wine_type, brand=best_match.winery, region=best_match.region,
                    varietal=best_match.varietal, description=best_match.description, wine_id=best_match.id,
                )
                # Add non-winning FTS candidates as near-misses
                for fts_result in fts_results:
                    if fts_result.canonical_name != best_match.canonical_name:
                        s = self._compute_fuzzy_score(query_lower, fts_result.canonical_name.lower())
                        if NearMiss(wine_name=fts_result.canonical_name, score=s, rejection_reason="below_threshold") not in all_near_misses:
                            all_near_misses.append(NearMiss(wine_name=fts_result.canonical_name, score=s, rejection_reason="not_best"))
                all_near_misses.sort(key=lambda x: x.score, reverse=True)
                return FuzzyMatchDebugResult(match=match, near_misses=all_near_misses[:5], fts_candidates_count=fts_count, rejection_reason=None)

        # Step 3: Fuzzy match (OR-based FTS)
        candidates = self._repository.search_fts_or(query_lower, limit=50)
        or_fts_count = len(candidates) + fts_count

        if not candidates:
            all_near_misses.sort(key=lambda x: x.score, reverse=True)
            return FuzzyMatchDebugResult(match=None, near_misses=all_near_misses[:5], fts_candidates_count=or_fts_count, rejection_reason="no_fts_candidates" if or_fts_count == 0 else "below_threshold")

        best_match = None
        best_score = 0.0
        for wine in candidates:
            score = self._compute_fuzzy_score(query_lower, wine.canonical_name.lower())
            if score > best_score:
                best_score = score
                best_match = wine
            # Track all candidates as potential near-misses
            reason = "below_threshold" if score < Config.FUZZY_CONFIDENCE_THRESHOLD else "not_best"
            all_near_misses.append(NearMiss(wine_name=wine.canonical_name, score=score, rejection_reason=reason))

        if best_match and best_score >= Config.FUZZY_CONFIDENCE_THRESHOLD:
            if _is_generic_query(best_match.canonical_name):
                all_near_misses.sort(key=lambda x: x.score, reverse=True)
                return FuzzyMatchDebugResult(match=None, near_misses=all_near_misses[:5], fts_candidates_count=or_fts_count, rejection_reason="generic_query")

            ratio = fuzz.ratio(query_lower, best_match.canonical_name.lower()) / 100.0
            partial_ratio = fuzz.partial_ratio(query_lower, best_match.canonical_name.lower()) / 100.0
            token_sort = fuzz.token_sort_ratio(query_lower, best_match.canonical_name.lower()) / 100.0
            phonetic = best_score - (Config.WEIGHT_RATIO * ratio + Config.WEIGHT_PARTIAL * partial_ratio + Config.WEIGHT_TOKEN_SORT * token_sort)
            scores = FuzzyScores(ratio=ratio, partial_ratio=partial_ratio, token_sort_ratio=token_sort, phonetic_bonus=max(0, phonetic), weighted_score=best_score)
            match = WineMatchWithScores(
                canonical_name=best_match.canonical_name, rating=best_match.rating,
                confidence=best_score, source=WineSource.DATABASE, scores=scores,
                wine_type=best_match.wine_type, brand=best_match.winery, region=best_match.region,
                varietal=best_match.varietal, description=best_match.description, wine_id=best_match.id,
            )
            # Remove the winning match from near-misses
            all_near_misses = [nm for nm in all_near_misses if nm.wine_name != best_match.canonical_name]
            all_near_misses.sort(key=lambda x: x.score, reverse=True)
            return FuzzyMatchDebugResult(match=match, near_misses=all_near_misses[:5], fts_candidates_count=or_fts_count, rejection_reason=None)

        all_near_misses.sort(key=lambda x: x.score, reverse=True)
        return FuzzyMatchDebugResult(match=None, near_misses=all_near_misses[:5], fts_candidates_count=or_fts_count, rejection_reason="below_threshold")

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
        # Clear match cache when reloading
        self.clear_cache()

    @staticmethod
    def clear_cache():
        """Clear the module-level match cache."""
        with _cache_lock:
            _match_cache.clear()

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
