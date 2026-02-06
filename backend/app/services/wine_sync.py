"""
Wine auto-sync service.

Automatically writes LLM/Vision-discovered wines back to the main database
so they are available for future fuzzy matching without LLM calls.
Runs silently after each scan — all errors are caught and logged, never
surfaced to the user.
"""

import logging
import re
from typing import Optional

from ..models.enums import RatingSource, WineSource

logger = logging.getLogger(__name__)


def _is_valid_wine_name(wine_name: str) -> bool:
    """Reject OCR garbage before writing to the database."""
    if len(wine_name) > 100:
        logger.debug(f"Skipping sync: name too long ({len(wine_name)} chars): '{wine_name[:50]}...'")
        return False

    word_count = len(wine_name.split())
    if word_count > 15:
        logger.debug(f"Skipping sync: too many words ({word_count}): '{wine_name[:50]}...'")
        return False

    # Count tokens that contain non-alphabetic characters as a garbage signal
    non_alpha_words = sum(1 for w in wine_name.split() if not re.match(r'^[A-Za-zÀ-ÿ\'-]+$', w))
    if non_alpha_words > 2:
        logger.debug(f"Skipping sync: likely OCR garbage: '{wine_name[:50]}...'")
        return False

    return True


def sync_discovered_wines(results: list, fallback: Optional[list] = None) -> int:
    """
    Persist LLM/Vision-discovered wines to the main database.

    Iterates over scan results and writes any wine whose source is not
    DATABASE into the wines table.  Also removes the corresponding
    llm_ratings_cache entry (if any) since the wine now lives in the
    canonical store.

    This function **never raises** — every error is caught and logged.

    Args:
        results: List of WineResult objects from the scan response.
        fallback: Optional list of FallbackWine objects.

    Returns:
        Number of wines successfully synced.
    """
    synced = 0

    try:
        # Lazy imports to avoid circular deps and keep startup fast
        from .wine_repository import WineRepository
        from .llm_rating_cache import get_llm_rating_cache

        repo = WineRepository()
        cache = get_llm_rating_cache()

        for wine in results:
            try:
                # Only sync wines not already from the database
                if getattr(wine, 'source', None) == WineSource.DATABASE:
                    continue

                wine_name = getattr(wine, 'wine_name', None)
                rating = getattr(wine, 'rating', None)

                if not wine_name or rating is None:
                    continue

                # Validate wine name to prevent OCR garbage from polluting DB
                if not _is_valid_wine_name(wine_name):
                    continue

                # Skip if already in DB (another scan may have synced it)
                if repo.exists(wine_name):
                    continue

                # Determine source label
                source = getattr(wine, 'source', WineSource.LLM)
                source_name = f"{source.value}_discovered"

                wine_id = repo.add_wine(
                    canonical_name=wine_name,
                    rating=rating,
                    wine_type=getattr(wine, 'wine_type', None),
                    region=getattr(wine, 'region', None),
                    winery=getattr(wine, 'brand', None),
                    varietal=getattr(wine, 'varietal', None),
                    source_name=source_name,
                    original_rating=rating,
                    original_scale=(1.0, 5.0),
                )

                logger.info(
                    f"Auto-synced wine to DB: '{wine_name}' "
                    f"(id={wine_id}, rating={rating}, source={source_name})"
                )

                # Remove from LLM cache now that it's in the main DB
                try:
                    cache.delete(wine_name)
                except Exception:
                    pass  # Non-critical

                synced += 1

            except Exception as exc:
                logger.debug(f"Skipped syncing wine '{getattr(wine, 'wine_name', '?')}': {exc}")

        # Also sync fallback wines that came from LLM
        if fallback:
            for fw in fallback:
                try:
                    wine_name = getattr(fw, 'wine_name', None)
                    rating = getattr(fw, 'rating', None)

                    if not wine_name or rating is None:
                        continue

                    # Validate wine name to prevent OCR garbage from polluting DB
                    if not _is_valid_wine_name(wine_name):
                        continue

                    if repo.exists(wine_name):
                        continue

                    # Fallback wines don't carry source metadata — check the cache
                    # to see if they were LLM-discovered
                    cached = cache.get(wine_name, increment_hit=False)
                    if cached is None:
                        # Not in LLM cache → likely already a DB wine, skip
                        continue

                    wine_id = repo.add_wine(
                        canonical_name=wine_name,
                        rating=rating,
                        wine_type=cached.wine_type,
                        region=cached.region,
                        winery=cached.brand,
                        varietal=cached.varietal,
                        source_name="llm_discovered",
                        original_rating=rating,
                        original_scale=(1.0, 5.0),
                    )

                    logger.info(
                        f"Auto-synced fallback wine to DB: '{wine_name}' "
                        f"(id={wine_id}, rating={rating})"
                    )

                    try:
                        cache.delete(wine_name)
                    except Exception:
                        pass

                    synced += 1

                except Exception as exc:
                    logger.debug(f"Skipped syncing fallback wine '{getattr(fw, 'wine_name', '?')}': {exc}")

    except Exception as exc:
        logger.warning(f"Wine auto-sync failed (non-fatal): {exc}")

    if synced:
        logger.info(f"Wine auto-sync complete: {synced} wine(s) added to database")

    return synced
