"""
Wine name matching against ratings database.

Uses multi-algorithm fuzzy matching:
- rapidfuzz for ratio, partial_ratio, token_sort_ratio
- jellyfish for phonetic matching (handles OCR errors)
- n-gram matching for partial text fragments

Supports both JSON and SQLite backends:
- JSON: Legacy mode (ratings.json)
- SQLite: New mode with WineRepository
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import jellyfish
from rapidfuzz import fuzz, process

from ..config import Config

if TYPE_CHECKING:
    from .wine_repository import WineRepository


@dataclass
class FuzzyScores:
    """Individual scores from fuzzy matching algorithms."""
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
    """A matched wine with detailed fuzzy matching scores."""
    canonical_name: str
    rating: float
    confidence: float
    source: str
    scores: FuzzyScores


class WineMatcher:
    """
    Enhanced fuzzy matcher for wine names.

    Uses a weighted combination of algorithms:
    - ratio (30%): Overall character similarity
    - partial_ratio (50%): Best substring match (handles fragments)
    - token_sort_ratio (20%): Word-order-independent matching

    Plus phonetic matching for OCR error tolerance.
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

        if repository is not None:
            # Use provided repository
            self.database = {"wines": repository.get_all_as_dict()}
        elif use_sqlite:
            # Create repository automatically
            from .wine_repository import WineRepository
            self._repository = WineRepository()
            self.database = {"wines": self._repository.get_all_as_dict()}
        else:
            # Legacy JSON mode
            if database_path is None:
                database_path = Path(__file__).parent.parent / "data" / "ratings.json"
            self.database = self._load_database(database_path)

        self._build_index()

    def _load_database(self, path: Path) -> dict:
        """Load ratings database from JSON file."""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            # Return empty database if file doesn't exist
            return {"wines": []}

    def _build_index(self) -> None:
        """Build lookup index for faster matching."""
        self.name_to_wine: dict[str, dict] = {}
        self.all_names: list[str] = []
        self.phonetic_index: dict[str, list[str]] = {}  # Metaphone → wine names
        self.ngram_index: dict[str, set[str]] = {}     # 3-gram → wine names
        self.winery_to_wines: dict[str, list[dict]] = {}  # Winery name → list of wines

        for wine in self.database.get("wines", []):
            canonical = wine["canonical_name"].lower()
            self._index_name(canonical, wine)

            # Index aliases too
            for alias in wine.get("aliases", []):
                alias_lower = alias.lower()
                self._index_name(alias_lower, wine)

            # Index winery name for brand/producer matching
            winery = wine.get("winery")
            if winery:
                winery_lower = winery.lower()
                if winery_lower not in self.winery_to_wines:
                    self.winery_to_wines[winery_lower] = []
                self.winery_to_wines[winery_lower].append(wine)
                # Also index winery as a matchable name
                if winery_lower not in self.name_to_wine:
                    # Map winery to first/best wine (highest rated)
                    self._index_name(winery_lower, wine)

    def _index_name(self, name: str, wine: dict) -> None:
        """Index a single name (canonical or alias)."""
        self.name_to_wine[name] = wine
        self.all_names.append(name)

        # Phonetic index (metaphone)
        try:
            metaphone = jellyfish.metaphone(name)
            if metaphone not in self.phonetic_index:
                self.phonetic_index[metaphone] = []
            self.phonetic_index[metaphone].append(name)
        except Exception:
            pass  # Skip if phonetic encoding fails

        # N-gram index (3-grams for substring matching)
        for ngram in self._get_ngrams(name, 3):
            if ngram not in self.ngram_index:
                self.ngram_index[ngram] = set()
            self.ngram_index[ngram].add(name)

    def _get_ngrams(self, text: str, n: int = 3) -> list[str]:
        """Generate n-grams from text."""
        text = re.sub(r'[^a-z0-9]', '', text.lower())
        if len(text) < n:
            return [text] if text else []
        return [text[i:i+n] for i in range(len(text) - n + 1)]

    def match(self, query: str) -> Optional[WineMatch]:
        """
        Find best matching wine for a query string.

        Uses multi-algorithm scoring:
        1. Exact match (confidence 1.0)
        2. Exact winery match (confidence 0.9)
        3. Weighted fuzzy match (ratio + partial_ratio + token_sort_ratio)
        4. Phonetic bonus for similar-sounding matches

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

        # Step 1: Try exact match
        if result := self._try_exact_match(query_lower):
            return result

        # Step 2: Try exact winery match
        if result := self._try_winery_match(query_lower):
            return result

        # Step 3: Get candidates and fuzzy match
        candidates = self._select_candidates(query_lower)
        return self._fuzzy_match_candidates(query_lower, candidates)

    def _try_exact_match(self, query_lower: str) -> Optional[WineMatch]:
        """Try to find an exact match in the database."""
        if query_lower in self.name_to_wine:
            wine = self.name_to_wine[query_lower]
            return WineMatch(
                canonical_name=wine["canonical_name"],
                rating=wine["rating"],
                confidence=1.0,
                source=wine.get("source", "unknown")
            )
        return None

    def _try_winery_match(self, query_lower: str) -> Optional[WineMatch]:
        """Try to match by winery name, returning highest-rated wine from producer."""
        if query_lower in self.winery_to_wines:
            wines = self.winery_to_wines[query_lower]
            best_wine = max(wines, key=lambda w: w.get("rating", 0))
            return WineMatch(
                canonical_name=best_wine["canonical_name"],
                rating=best_wine["rating"],
                confidence=0.9,  # High confidence for exact winery match
                source=best_wine.get("source", "unknown")
            )
        return None

    def _select_candidates(self, query_lower: str) -> set[str]:
        """Select candidate wines for fuzzy matching using n-gram or prefix index."""
        candidates = self._get_candidates(query_lower)
        if not candidates:
            candidates = self._get_prefix_candidates(query_lower)
        return candidates

    def _fuzzy_match_candidates(
        self,
        query_lower: str,
        candidates: set[str]
    ) -> Optional[WineMatch]:
        """
        Fuzzy match query against candidates.

        Uses optimized batch processing for large candidate sets,
        and manual matching with phonetic bonus for small sets.
        """
        if not candidates:
            return None

        if len(candidates) > Config.CANDIDATE_LARGE_THRESHOLD:
            best_match, best_score = self._fuzzy_match_large_set(query_lower, candidates)
        else:
            best_match, best_score = self._fuzzy_match_small_set(query_lower, candidates)

        if best_match:
            return WineMatch(
                canonical_name=best_match["canonical_name"],
                rating=best_match["rating"],
                confidence=best_score,
                source=best_match.get("source", "unknown")
            )
        return None

    def _fuzzy_match_large_set(
        self,
        query_lower: str,
        candidates: set[str]
    ) -> tuple[Optional[dict], float]:
        """Fuzzy match using rapidfuzz batch processing for large candidate sets."""
        results = process.extract(
            query_lower,
            candidates,
            scorer=fuzz.WRatio,
            score_cutoff=Config.MIN_SIMILARITY * 100,
            limit=10
        )

        best_match = None
        best_score = 0.0

        for name, score, _ in results:
            adjusted_score = self._apply_length_penalty(query_lower, name, score / 100)

            if adjusted_score > best_score and adjusted_score >= Config.MIN_SIMILARITY:
                best_score = adjusted_score
                best_match = self.name_to_wine[name]

        return best_match, best_score

    def _fuzzy_match_small_set(
        self,
        query_lower: str,
        candidates: set[str]
    ) -> tuple[Optional[dict], float]:
        """Fuzzy match with phonetic bonus for small candidate sets."""
        best_match = None
        best_score = 0.0

        try:
            query_metaphone = jellyfish.metaphone(query_lower)
        except Exception:
            query_metaphone = None

        for name in candidates:
            score = self._enhanced_similarity(query_lower, name, query_metaphone)
            if score > best_score and score >= Config.MIN_SIMILARITY:
                best_score = score
                best_match = self.name_to_wine[name]

            # Early exit if we found an excellent match
            if best_score >= Config.FUZZY_EARLY_EXIT:
                break

        return best_match, best_score

    def _apply_length_penalty(
        self,
        query_lower: str,
        candidate: str,
        base_score: float
    ) -> float:
        """Apply length penalty to prevent short candidate matches on long queries."""
        candidate_main = candidate.split()[0] if candidate else candidate
        query_main = query_lower.split()[0] if query_lower else query_lower
        len_ratio = len(candidate_main) / max(len(query_main), 1)

        # Only apply penalties if query is NOT contained in candidate
        if query_lower in candidate:
            return base_score

        adjusted_score = base_score
        if len_ratio < 0.5:
            adjusted_score = max(0, adjusted_score - 0.4)
        elif len_ratio < 0.7:
            adjusted_score = max(0, adjusted_score - 0.2)

        # Also penalize if raw ratio is too low
        raw_ratio = fuzz.ratio(query_lower, candidate) / 100
        if raw_ratio < 0.4:
            adjusted_score = adjusted_score * 0.5

        return adjusted_score

    def _get_candidates(self, query: str) -> set[str]:
        """Get candidate names using n-gram index."""
        candidates = set()
        query_ngrams = self._get_ngrams(query, 3)

        for ngram in query_ngrams:
            if ngram in self.ngram_index:
                candidates.update(self.ngram_index[ngram])

        return candidates

    def _get_prefix_candidates(self, query: str, max_candidates: int = 500) -> set[str]:
        """Get candidates by prefix matching when n-gram fails."""
        candidates = set()

        # Try progressively shorter prefixes
        for prefix_len in [4, 3, 2]:
            if len(query) >= prefix_len:
                prefix = query[:prefix_len]
                for name in self.all_names:
                    if name.startswith(prefix):
                        candidates.add(name)
                        if len(candidates) >= max_candidates:
                            return candidates

                # Also check phonetic prefix
                if hasattr(self, 'phonetic_index'):
                    try:
                        query_metaphone = jellyfish.metaphone(query)
                        if query_metaphone:
                            mp_prefix = query_metaphone[:prefix_len]
                            for mp, names in self.phonetic_index.items():
                                if mp.startswith(mp_prefix):
                                    candidates.update(names)
                                    if len(candidates) >= max_candidates:
                                        return candidates
                    except Exception:
                        pass

            if candidates:
                return candidates

        return candidates

    def _enhanced_similarity(
        self,
        query: str,
        candidate: str,
        query_metaphone: Optional[str] = None
    ) -> float:
        """
        Calculate enhanced similarity using multiple algorithms.

        Combines:
        - ratio (30%): Overall character similarity
        - partial_ratio (50%): Best substring match (key for fragments like "aymus" → "caymus")
        - token_sort_ratio (20%): Word-order-independent

        Plus phonetic bonus for OCR error tolerance.

        Applies length penalty to prevent short database names from matching
        long queries (e.g., "Vennstone" should not match "One").
        """
        # Core fuzzy scores (rapidfuzz returns 0-100)
        ratio_score = fuzz.ratio(query, candidate) / 100
        partial_score = fuzz.partial_ratio(query, candidate) / 100
        token_sort_score = fuzz.token_sort_ratio(query, candidate) / 100

        # Weighted combination
        base_score = (
            Config.WEIGHT_RATIO * ratio_score +
            Config.WEIGHT_PARTIAL * partial_score +
            Config.WEIGHT_TOKEN_SORT * token_sort_score
        )

        # Check if query is contained in candidate (good: "Crimson Ranch" in "Crimson Ranch 2014 Cab...")
        query_in_candidate = query in candidate

        # Length penalty: penalize when candidate is much shorter than query
        # AND query is not contained in candidate
        # This prevents "Vennstone" → "One" (substring match abuse)
        if not query_in_candidate:
            candidate_main = candidate.split()[0] if candidate else candidate
            query_main = query.split()[0] if query else query

            len_ratio = len(candidate_main) / max(len(query_main), 1)
            if len_ratio < 0.5:
                # Candidate main word is less than half query length - heavy penalty
                base_score = max(0, base_score - 0.4)
            elif len_ratio < 0.7:
                # Moderate length mismatch
                base_score = max(0, base_score - 0.2)

            # Also penalize if overall character similarity is too low
            # This prevents false matches like "Vennstone" → "Overstone"
            if ratio_score < 0.4:
                base_score = base_score * 0.5

        # Phonetic bonus
        phonetic_bonus = 0.0
        if query_metaphone:
            try:
                candidate_metaphone = jellyfish.metaphone(candidate)
                if query_metaphone == candidate_metaphone:
                    phonetic_bonus = Config.PHONETIC_BONUS
                elif jellyfish.jaro_winkler_similarity(
                    query_metaphone, candidate_metaphone
                ) > 0.8:
                    phonetic_bonus = Config.PHONETIC_BONUS * 0.5
            except Exception:
                pass

        return min(1.0, base_score + phonetic_bonus)

    def match_with_scores(self, query: str) -> Optional[WineMatchWithScores]:
        """
        Find best matching wine with detailed fuzzy matching scores.

        Args:
            query: Normalized wine name from OCR

        Returns:
            WineMatchWithScores if found, None otherwise
        """
        if not query:
            return None

        query_lower = query.lower().strip()

        if len(query_lower) < 3:
            return None

        # Try exact match first
        if query_lower in self.name_to_wine:
            wine = self.name_to_wine[query_lower]
            return WineMatchWithScores(
                canonical_name=wine["canonical_name"],
                rating=wine["rating"],
                confidence=1.0,
                source=wine.get("source", "unknown"),
                scores=FuzzyScores(
                    ratio=1.0,
                    partial_ratio=1.0,
                    token_sort_ratio=1.0,
                    phonetic_bonus=0.0,
                    weighted_score=1.0
                )
            )

        # Get candidates and find best match with scores
        candidates = self._get_candidates(query_lower)
        if not candidates:
            candidates = self._get_prefix_candidates(query_lower)

        best_match = None
        best_score = 0
        best_scores = None

        try:
            query_metaphone = jellyfish.metaphone(query_lower)
        except Exception:
            query_metaphone = None

        for name in candidates:
            scores = self._get_similarity_scores(query_lower, name, query_metaphone)
            if scores.weighted_score > best_score and scores.weighted_score >= Config.MIN_SIMILARITY:
                best_score = scores.weighted_score
                best_match = self.name_to_wine[name]
                best_scores = scores

            if best_score >= 0.95:
                break

        if best_match and best_scores:
            return WineMatchWithScores(
                canonical_name=best_match["canonical_name"],
                rating=best_match["rating"],
                confidence=best_score,
                source=best_match.get("source", "unknown"),
                scores=best_scores
            )

        return None

    def _get_similarity_scores(
        self,
        query: str,
        candidate: str,
        query_metaphone: Optional[str] = None
    ) -> FuzzyScores:
        """
        Calculate individual similarity scores for debugging.

        Returns FuzzyScores with all individual algorithm scores.
        """
        # Core fuzzy scores (rapidfuzz returns 0-100)
        ratio_score = fuzz.ratio(query, candidate) / 100
        partial_score = fuzz.partial_ratio(query, candidate) / 100
        token_sort_score = fuzz.token_sort_ratio(query, candidate) / 100

        # Weighted combination
        base_score = (
            Config.WEIGHT_RATIO * ratio_score +
            Config.WEIGHT_PARTIAL * partial_score +
            Config.WEIGHT_TOKEN_SORT * token_sort_score
        )

        # Check if query is contained in candidate
        query_in_candidate = query in candidate

        # Length penalty
        if not query_in_candidate:
            candidate_main = candidate.split()[0] if candidate else candidate
            query_main = query.split()[0] if query else query

            len_ratio = len(candidate_main) / max(len(query_main), 1)
            if len_ratio < 0.5:
                base_score = max(0, base_score - 0.4)
            elif len_ratio < 0.7:
                base_score = max(0, base_score - 0.2)

            if ratio_score < 0.4:
                base_score = base_score * 0.5

        # Phonetic bonus
        phonetic_bonus = 0.0
        if query_metaphone:
            try:
                candidate_metaphone = jellyfish.metaphone(candidate)
                if query_metaphone == candidate_metaphone:
                    phonetic_bonus = Config.PHONETIC_BONUS
                elif jellyfish.jaro_winkler_similarity(
                    query_metaphone, candidate_metaphone
                ) > 0.8:
                    phonetic_bonus = Config.PHONETIC_BONUS * 0.5
            except Exception:
                pass

        return FuzzyScores(
            ratio=ratio_score,
            partial_ratio=partial_score,
            token_sort_ratio=token_sort_score,
            phonetic_bonus=phonetic_bonus,
            weighted_score=min(1.0, base_score + phonetic_bonus)
        )

    def match_many(self, queries: list[str]) -> list[Optional[WineMatch]]:
        """Match multiple queries."""
        return [self.match(q) for q in queries]

    def get_all_wines(self) -> list[dict]:
        """Return all wines in the database."""
        return self.database.get("wines", [])

    def reload(self):
        """Reload database and rebuild index (useful after ingestion)."""
        if self._repository:
            self.database = {"wines": self._repository.get_all_as_dict()}
        self._build_index()

    def wine_count(self) -> int:
        """Return total number of wines in database."""
        return len(self.database.get("wines", []))
