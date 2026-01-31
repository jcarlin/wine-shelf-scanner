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
class WineMatch:
    """A matched wine from the database."""
    canonical_name: str
    rating: float
    confidence: float  # Match confidence (0-1)
    source: str


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

    def _load_database(self, path) -> dict:
        """Load ratings database from JSON file."""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            # Return empty database if file doesn't exist
            return {"wines": []}

    def _build_index(self):
        """Build lookup index for faster matching."""
        self.name_to_wine = {}
        self.all_names = []
        self.phonetic_index = {}  # Metaphone → wine names
        self.ngram_index = {}     # 3-gram → wine names

        for wine in self.database.get("wines", []):
            canonical = wine["canonical_name"].lower()
            self._index_name(canonical, wine)

            # Index aliases too
            for alias in wine.get("aliases", []):
                alias_lower = alias.lower()
                self._index_name(alias_lower, wine)

    def _index_name(self, name: str, wine: dict):
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
        2. Weighted fuzzy match (ratio + partial_ratio + token_sort_ratio)
        3. Phonetic bonus for similar-sounding matches

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

        # Try exact match first
        if query_lower in self.name_to_wine:
            wine = self.name_to_wine[query_lower]
            return WineMatch(
                canonical_name=wine["canonical_name"],
                rating=wine["rating"],
                confidence=1.0,
                source=wine.get("source", "unknown")
            )

        # Get candidate set using n-gram index (faster than checking all)
        candidates = self._get_candidates(query_lower)

        # If no n-gram matches, use prefix matching instead of all names
        if not candidates:
            candidates = self._get_prefix_candidates(query_lower)

        # Use rapidfuzz's optimized batch processing for large candidate sets
        if len(candidates) > 100:
            # Use process.extractOne for fast matching
            result = process.extractOne(
                query_lower,
                candidates,
                scorer=fuzz.WRatio,  # Weighted ratio - good balance
                score_cutoff=Config.MIN_SIMILARITY * 100
            )
            if result:
                name, score, _ = result
                best_score = score / 100
                best_match = self.name_to_wine[name]
            else:
                best_match = None
                best_score = 0
        else:
            # Manual matching for small candidate sets (allows phonetic bonus)
            best_match = None
            best_score = 0

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
                if best_score >= 0.95:
                    break

        if best_match:
            return WineMatch(
                canonical_name=best_match["canonical_name"],
                rating=best_match["rating"],
                confidence=best_score,
                source=best_match.get("source", "unknown")
            )

        return None

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
