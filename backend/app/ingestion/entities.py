"""
Entity resolution for wine data.

Handles deduplication and merging of wine records from multiple sources.
Uses multi-pass matching:
- Pass 1: Exact match on normalized name
- Pass 2: Fuzzy match with blocking (rapidfuzz)
- Pass 3: Phonetic match (jellyfish metaphone)
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from rapidfuzz import fuzz
import jellyfish


@dataclass
class CanonicalWine:
    """
    A canonical wine entity resolved from one or more sources.

    Aggregates ratings from multiple sources with weighted averaging.
    """
    canonical_name: str
    normalized_rating: float
    wine_type: Optional[str] = None
    region: Optional[str] = None
    winery: Optional[str] = None
    country: Optional[str] = None
    varietal: Optional[str] = None

    # Source tracking
    sources: dict[str, float] = field(default_factory=dict)  # source_name → normalized_rating
    aliases: set[str] = field(default_factory=set)

    # Original data for provenance
    original_ratings: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    # source_name → (original_rating, scale_min, scale_max)

    def add_source(
        self,
        source_name: str,
        normalized_rating: float,
        original_rating: float,
        original_scale: tuple[float, float]
    ):
        """Add a rating source to this wine."""
        self.sources[source_name] = normalized_rating
        self.original_ratings[source_name] = (
            original_rating,
            original_scale[0],
            original_scale[1]
        )
        # Recalculate aggregated rating
        self._recalculate_rating()

    def add_alias(self, alias: str):
        """Add an alternate name for this wine."""
        normalized = self._normalize_for_matching(alias)
        if normalized != self._normalize_for_matching(self.canonical_name):
            self.aliases.add(alias)

    def _recalculate_rating(self):
        """Recalculate rating from sources with weighting."""
        if not self.sources:
            return

        # Source reliability weights (can be configured)
        weights = {
            "vivino": 0.5,
            "kaggle_wine_reviews": 0.5,
            "wine_enthusiast": 0.6,
            "wine_spectator": 0.6,
        }

        total_weight = 0
        weighted_sum = 0

        for source, rating in self.sources.items():
            weight = weights.get(source, 0.4)  # Default weight
            weighted_sum += rating * weight
            total_weight += weight

        if total_weight > 0:
            self.normalized_rating = round(weighted_sum / total_weight, 2)

    @staticmethod
    def _normalize_for_matching(name: str) -> str:
        """Normalize name for comparison."""
        # Lowercase, remove punctuation, collapse whitespace
        name = name.lower()
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name


class WineEntityResolver:
    """
    Resolves wine records into canonical entities.

    Pass 1: Exact match on normalized name
    Pass 2: Fuzzy match (optional, Phase 6.4)
    Pass 3: Phonetic match (optional, Phase 6.4)
    """

    def __init__(self, fuzzy_threshold: float = 0.80, enable_fuzzy: bool = False):
        """
        Initialize resolver.

        Args:
            fuzzy_threshold: Minimum similarity for fuzzy matching
            enable_fuzzy: Whether to use fuzzy matching (Phase 6.4)
        """
        self.fuzzy_threshold = fuzzy_threshold
        self.enable_fuzzy = enable_fuzzy

        # Index: normalized_name → CanonicalWine
        self._entities: dict[str, CanonicalWine] = {}
        # Reverse index: alias → canonical_name
        self._alias_index: dict[str, str] = {}

    def resolve(
        self,
        wine_name: str,
        normalized_rating: float,
        original_rating: float,
        original_scale: tuple[float, float],
        source_name: str,
        winery: Optional[str] = None,
        region: Optional[str] = None,
        country: Optional[str] = None,
        varietal: Optional[str] = None,
        wine_type: Optional[str] = None,
    ) -> tuple[CanonicalWine, bool]:
        """
        Resolve a wine record to a canonical entity.

        Args:
            wine_name: Name from source
            normalized_rating: Already-normalized rating (1-5)
            original_rating: Original rating value
            original_scale: (min, max) of original scale
            source_name: Name of the data source
            winery: Optional winery name
            region: Optional region
            country: Optional country
            varietal: Optional grape varietal
            wine_type: Optional type (red, white, etc.)

        Returns:
            Tuple of (CanonicalWine, is_new) where is_new indicates new entity
        """
        normalized_name = self._normalize_for_key(wine_name)

        # Pass 1: Exact match
        if normalized_name in self._entities:
            entity = self._entities[normalized_name]
            entity.add_source(source_name, normalized_rating, original_rating, original_scale)
            entity.add_alias(wine_name)
            self._update_metadata(entity, winery, region, country, varietal, wine_type)
            return entity, False

        # Check alias index
        if normalized_name in self._alias_index:
            canonical_key = self._alias_index[normalized_name]
            entity = self._entities[canonical_key]
            entity.add_source(source_name, normalized_rating, original_rating, original_scale)
            entity.add_alias(wine_name)
            self._update_metadata(entity, winery, region, country, varietal, wine_type)
            return entity, False

        # Pass 2: Fuzzy match (optional, enabled in Phase 6.4)
        if self.enable_fuzzy:
            match = self._fuzzy_match(wine_name)
            if match:
                match.add_source(source_name, normalized_rating, original_rating, original_scale)
                match.add_alias(wine_name)
                self._alias_index[normalized_name] = self._normalize_for_key(match.canonical_name)
                self._update_metadata(match, winery, region, country, varietal, wine_type)
                return match, False

        # Create new entity
        entity = CanonicalWine(
            canonical_name=wine_name,
            normalized_rating=normalized_rating,
            winery=winery,
            region=region,
            country=country,
            varietal=varietal,
            wine_type=wine_type,
        )
        entity.add_source(source_name, normalized_rating, original_rating, original_scale)

        self._entities[normalized_name] = entity
        return entity, True

    def get_all_entities(self) -> list[CanonicalWine]:
        """Get all resolved canonical wines."""
        return list(self._entities.values())

    def get_entity_count(self) -> int:
        """Get count of unique canonical wines."""
        return len(self._entities)

    def get_merge_count(self) -> int:
        """Get count of wines that were merged (have multiple sources)."""
        return sum(1 for e in self._entities.values() if len(e.sources) > 1)

    def _normalize_for_key(self, name: str) -> str:
        """Normalize wine name for index key."""
        # Lowercase
        name = name.lower()
        # Remove vintage years (4-digit numbers starting with 19 or 20)
        name = re.sub(r'\b(19|20)\d{2}\b', '', name)
        # Remove punctuation
        name = re.sub(r'[^\w\s]', '', name)
        # Collapse whitespace
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    def _update_metadata(
        self,
        entity: CanonicalWine,
        winery: Optional[str],
        region: Optional[str],
        country: Optional[str],
        varietal: Optional[str],
        wine_type: Optional[str],
    ):
        """Update entity metadata if not already set."""
        if winery and not entity.winery:
            entity.winery = winery
        if region and not entity.region:
            entity.region = region
        if country and not entity.country:
            entity.country = country
        if varietal and not entity.varietal:
            entity.varietal = varietal
        if wine_type and not entity.wine_type:
            entity.wine_type = wine_type

    def _fuzzy_match(self, wine_name: str) -> Optional[CanonicalWine]:
        """
        Find fuzzy match in existing entities.

        Uses blocking by first 2 characters to reduce comparisons,
        then applies fuzzy matching with rapidfuzz.

        Returns None if no match above threshold.
        """
        normalized = self._normalize_for_key(wine_name)
        if len(normalized) < 2:
            return None

        # Blocking: only compare wines starting with same 2 chars
        prefix = normalized[:2]
        candidates = [
            (key, entity)
            for key, entity in self._entities.items()
            if key.startswith(prefix)
        ]

        if not candidates:
            # Try phonetic matching as fallback
            return self._phonetic_match(wine_name)

        best_match = None
        best_score = 0

        for key, entity in candidates:
            # Multi-algorithm scoring
            # For entity resolution, weight partial_ratio more heavily
            # to catch "Opus One" matching "Opus One Napa Valley"
            ratio_score = fuzz.ratio(normalized, key) / 100
            partial_score = fuzz.partial_ratio(normalized, key) / 100
            token_sort_score = fuzz.token_sort_ratio(normalized, key) / 100

            # Check if one is a substring of the other (common pattern)
            is_substring = normalized in key or key in normalized

            # Weighted combination (heavier partial weight for entity resolution)
            base_score = (
                0.20 * ratio_score +
                0.60 * partial_score +
                0.20 * token_sort_score
            )

            # Boost score if one is a substring (likely same wine)
            score = min(1.0, base_score + (0.10 if is_substring else 0))

            if score > best_score and score >= self.fuzzy_threshold:
                best_score = score
                best_match = entity

        return best_match

    def _phonetic_match(self, wine_name: str) -> Optional[CanonicalWine]:
        """
        Find phonetic match using Metaphone.

        Helps with OCR-like variations (e.g., "Kaymus" → "Caymus").
        """
        try:
            query_metaphone = jellyfish.metaphone(wine_name.lower())
        except Exception:
            return None

        if not query_metaphone or len(query_metaphone) < 3:
            return None

        # Build phonetic index on first use
        if not hasattr(self, '_phonetic_index'):
            self._phonetic_index: dict[str, list[str]] = {}
            for key in self._entities.keys():
                try:
                    mp = jellyfish.metaphone(key)
                    if mp:
                        if mp not in self._phonetic_index:
                            self._phonetic_index[mp] = []
                        self._phonetic_index[mp].append(key)
                except Exception:
                    pass

        # Look up by phonetic code
        if query_metaphone in self._phonetic_index:
            candidates = self._phonetic_index[query_metaphone]
            if candidates:
                # Return first match (could rank by other criteria)
                return self._entities[candidates[0]]

        return None

    def clear(self):
        """Clear all resolved entities."""
        self._entities.clear()
        self._alias_index.clear()
        if hasattr(self, '_phonetic_index'):
            self._phonetic_index.clear()
