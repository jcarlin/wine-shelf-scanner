"""
Centralized configuration for the Wine Shelf Scanner backend.

All constants are defined here to avoid scattered magic numbers
and enable easy configuration management.
"""

import os
from typing import List, Optional


class Config:
    """Application configuration constants."""

    # === Confidence Thresholds ===
    # These match the UX rules in CLAUDE.md
    VISIBILITY_THRESHOLD = 0.45       # Show in results (opacity 0.5)
    TAPPABLE_THRESHOLD = 0.65         # Enable detail tap (opacity 0.75)
    HIGH_CONFIDENCE_THRESHOLD = 0.85  # "Widely rated" label (opacity 1.0)
    FUZZY_CONFIDENCE_THRESHOLD = 0.7  # Trigger LLM fallback
    FUZZY_EARLY_EXIT = 0.95           # Skip remaining candidates

    # === Fuzzy Matching Weights ===
    # Multi-algorithm scoring: ratio + partial_ratio + token_sort_ratio
    WEIGHT_RATIO = 0.30
    WEIGHT_PARTIAL = 0.50
    WEIGHT_TOKEN_SORT = 0.20
    PHONETIC_BONUS = 0.10
    MIN_SIMILARITY = 0.6

    # === OCR Processing ===
    PROXIMITY_THRESHOLD = 0.15  # Text must be within this distance of bottle
    MIN_TEXT_LENGTH = 3
    MAX_TEXT_LENGTH = 50
    DEFAULT_IMAGE_WIDTH = 1000
    DEFAULT_IMAGE_HEIGHT = 1000

    # === Performance ===
    CANDIDATE_LARGE_THRESHOLD = 100  # Use optimized batch processing above this
    MAX_CANDIDATES = 500             # Max candidates for prefix matching

    # === Environment ===
    @staticmethod
    def use_mocks() -> bool:
        """Check if mock mode is enabled."""
        return os.getenv("USE_MOCKS", "false").lower() == "true"

    @staticmethod
    def anthropic_api_key() -> Optional[str]:
        """Get Anthropic API key from environment."""
        return os.getenv("ANTHROPIC_API_KEY")

    @staticmethod
    def use_sqlite() -> bool:
        """Use SQLite database (191K wines) vs JSON (60 wines)."""
        return os.getenv("USE_SQLITE", "true").lower() == "true"

    # === Security ===
    MAX_IMAGE_SIZE_MB = 10
    MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
    ALLOWED_CONTENT_TYPES: List[str] = ["image/jpeg", "image/png"]
