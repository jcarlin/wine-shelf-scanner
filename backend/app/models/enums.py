"""
Enums for type-safe string constants in Wine Shelf Scanner.
"""

from enum import Enum


class WineSource(str, Enum):
    """Source of wine identification."""
    DATABASE = "database"
    LLM = "llm"
    VISION = "vision"  # Identified via Claude Vision (image analysis)


class RatingSource(str, Enum):
    """Source of wine rating."""
    DATABASE = "database"
    LLM_ESTIMATED = "llm_estimated"
    DEFAULT = "default"  # Fallback rating when LLM couldn't estimate
    NONE = "none"
