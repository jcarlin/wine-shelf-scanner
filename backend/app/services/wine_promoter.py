"""
Wine Promoter Service.

Manages promotion of frequently-requested LLM-estimated wines to the main database.
Provides workflow for reviewing, promoting, or rejecting cached wine candidates.
"""

import logging
from typing import Optional

from .llm_rating_cache import LLMRatingCache, CachedRating, get_llm_rating_cache
from .wine_repository import WineRepository

logger = logging.getLogger(__name__)


class WinePromoter:
    """
    Manages promotion of cached LLM-rated wines to the main database.

    Wines that are frequently requested (hit count >= threshold) become
    promotion candidates. This class provides methods to:
    - List candidates for review
    - Promote wines to the main database
    - Reject bad candidates (remove from cache)
    - View statistics
    """

    def __init__(
        self,
        cache: Optional[LLMRatingCache] = None,
        repo: Optional[WineRepository] = None
    ):
        """
        Initialize WinePromoter.

        Args:
            cache: LLMRatingCache instance. Lazy-initialized if not provided.
            repo: WineRepository instance. Lazy-initialized if not provided.
        """
        self._cache = cache
        self._repo = repo

    @property
    def cache(self) -> LLMRatingCache:
        """Get cache instance, lazy-initializing if needed."""
        if self._cache is None:
            self._cache = get_llm_rating_cache()
        return self._cache

    @property
    def repo(self) -> WineRepository:
        """Get repository instance, lazy-initializing if needed."""
        if self._repo is None:
            self._repo = WineRepository()
        return self._repo

    def get_candidates(self, min_hits: int = 5) -> list[CachedRating]:
        """
        Get wines that are candidates for promotion to the main database.

        Args:
            min_hits: Minimum hit count to qualify as a candidate (default: 5)

        Returns:
            List of CachedRating objects sorted by hit_count descending
        """
        return self.cache.get_promotion_candidates(min_hits=min_hits)

    def promote(self, wine_name: str) -> bool:
        """
        Promote a cached wine to the main wines table.

        Args:
            wine_name: Name of the wine to promote

        Returns:
            True if successfully promoted, False if wine not found in cache
        """
        # Get cached wine without incrementing hit count
        cached = self.cache.get(wine_name, increment_hit=False)

        if cached is None:
            logger.warning(f"Cannot promote wine '{wine_name}': not found in cache")
            return False

        # Add to main wines table
        try:
            wine_id = self.repo.add_wine(
                canonical_name=cached.wine_name,
                rating=cached.estimated_rating,
                wine_type=cached.wine_type,
                region=cached.region,
                winery=cached.brand,
                varietal=cached.varietal,
                source_name="llm_discovered",
                original_rating=cached.estimated_rating,
                original_scale=(1.0, 5.0),
            )

            logger.info(
                f"Promoted wine '{cached.wine_name}' to main database "
                f"(id={wine_id}, rating={cached.estimated_rating:.1f}, "
                f"hits={cached.hit_count})"
            )

            # Remove from cache after successful promotion
            self.cache.delete(wine_name)

            return True

        except Exception as e:
            logger.error(f"Failed to promote wine '{wine_name}': {e}")
            return False

    def reject(self, wine_name: str) -> bool:
        """
        Reject a cached wine (remove from cache).

        Use this for bad candidates that should not be promoted
        (e.g., OCR errors, non-wine items).

        Args:
            wine_name: Name of the wine to reject

        Returns:
            True if deleted, False if not found
        """
        deleted = self.cache.delete(wine_name)

        if deleted:
            logger.info(f"Rejected and removed wine '{wine_name}' from cache")
        else:
            logger.warning(f"Cannot reject wine '{wine_name}': not found in cache")

        return deleted

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with total_entries, total_hits, promotion_candidates
        """
        return self.cache.get_stats()


# Singleton instance
_promoter_instance: Optional[WinePromoter] = None


def get_wine_promoter() -> WinePromoter:
    """Get the singleton WinePromoter instance."""
    global _promoter_instance
    if _promoter_instance is None:
        _promoter_instance = WinePromoter()
    return _promoter_instance
