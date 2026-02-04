"""
Feature flags for Wine Shelf Scanner.

Uses pydantic-settings (FastAPI-recommended) for typed, validated,
environment-variable-backed feature flags.

Toggle via env vars: FEATURE_PAIRINGS=false
All flags default to True (on). Disable via env vars when needed.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class FeatureFlags(BaseSettings):
    """Feature flags backed by environment variables."""

    feature_wine_memory: bool = True
    feature_shelf_ranking: bool = True
    feature_safe_pick: bool = True
    feature_pairings: bool = True
    feature_trust_signals: bool = True

    model_config = {
        "env_prefix": "",
        "case_sensitive": False,
    }


@lru_cache()
def get_feature_flags() -> FeatureFlags:
    """Cached singleton. Use FastAPI Depends() for injection."""
    return FeatureFlags()
