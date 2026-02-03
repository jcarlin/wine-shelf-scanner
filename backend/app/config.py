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
    HIGH_CONFIDENCE_THRESHOLD = 0.80  # Skip LLM for high-confidence matches (was 0.85)
    FUZZY_CONFIDENCE_THRESHOLD = 0.72 # Accept fuzzy match (higher = fewer false positives)
    FUZZY_EARLY_EXIT = 0.95           # Skip remaining candidates

    # === Fuzzy Matching Weights ===
    # Multi-algorithm scoring: ratio + partial_ratio + token_sort_ratio
    # Higher ratio weight favors exact string matches over partial matches
    WEIGHT_RATIO = 0.45
    WEIGHT_PARTIAL = 0.30
    WEIGHT_TOKEN_SORT = 0.25
    PHONETIC_BONUS = 0.05
    MIN_SIMILARITY = 0.65

    # === OCR Processing ===
    PROXIMITY_THRESHOLD = 0.20  # Text must be within this distance of bottle
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
    def gemini_api_key() -> Optional[str]:
        """Get Google Gemini API key from environment."""
        return os.getenv("GOOGLE_API_KEY")

    @staticmethod
    def gemini_model() -> str:
        """Get Gemini model name. Default: gemini-2.0-flash."""
        return os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    @staticmethod
    def llm_provider() -> str:
        """Get LLM provider (claude or gemini). Default: gemini."""
        return os.getenv("LLM_PROVIDER", "gemini").lower()

    @staticmethod
    def openai_api_key() -> Optional[str]:
        """Get OpenAI API key from environment (optional fallback)."""
        return os.getenv("OPENAI_API_KEY")

    @staticmethod
    def use_litellm() -> bool:
        """Use LiteLLM unified interface (with automatic fallbacks). Default: True."""
        return os.getenv("USE_LITELLM", "true").lower() == "true"

    @staticmethod
    def use_sqlite() -> bool:
        """Use SQLite database (191K wines) vs JSON (60 wines)."""
        return os.getenv("USE_SQLITE", "true").lower() == "true"

    @staticmethod
    def log_level() -> str:
        """Log level (DEBUG, INFO, WARNING, ERROR)."""
        return os.getenv("LOG_LEVEL", "INFO").upper()

    @staticmethod
    def is_dev() -> bool:
        """Dev mode enables verbose logging."""
        return os.getenv("DEV_MODE", "false").lower() == "true"

    # === Vision Cache ===
    @staticmethod
    def vision_cache_enabled() -> bool:
        """Enable Vision API response caching."""
        return os.getenv("VISION_CACHE_ENABLED", "false").lower() == "true"

    @staticmethod
    def vision_cache_ttl_days() -> int:
        """Vision cache TTL in days (0 = no expiry)."""
        return int(os.getenv("VISION_CACHE_TTL_DAYS", "7"))

    @staticmethod
    def vision_cache_max_size_mb() -> int:
        """Maximum vision cache size in MB before LRU eviction."""
        return int(os.getenv("VISION_CACHE_MAX_SIZE_MB", "500"))

    # === LLM Rating Cache ===
    @staticmethod
    def use_llm_cache() -> bool:
        """Enable LLM rating cache for discovered wines. Default: False."""
        return os.getenv("USE_LLM_CACHE", "false").lower() == "true"

    # === Vision Fallback ===
    # Max confidence for visual-only identification (never top-3 emphasis)
    VISION_FALLBACK_CONFIDENCE_CAP = 0.70

    @staticmethod
    def use_vision_fallback() -> bool:
        """Enable Claude Vision fallback for unmatched bottles. Default: True."""
        return os.getenv("USE_VISION_FALLBACK", "true").lower() == "true"

    # === Security ===
    MAX_IMAGE_SIZE_MB = 10
    MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
    ALLOWED_CONTENT_TYPES: List[str] = [
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/heif",
    ]
