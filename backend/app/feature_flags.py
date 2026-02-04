"""
Feature flags for Wine Shelf Scanner.

Uses pydantic-settings (FastAPI-recommended) for typed, validated,
environment-variable-backed feature flags.

Toggle via env vars: FEATURE_PAIRINGS=true
All flags default to False (off) until explicitly enabled.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class FeatureFlags(BaseSettings):
    """Feature flags backed by environment variables."""

    feature_wine_memory: bool = False
    feature_shelf_ranking: bool = False
    feature_safe_pick: bool = False
    feature_pairings: bool = False

    model_config = {
        "env_prefix": "",
        "case_sensitive": False,
    }


@lru_cache()
def get_feature_flags() -> FeatureFlags:
    """Cached singleton. Use FastAPI Depends() for injection."""
    return FeatureFlags()
