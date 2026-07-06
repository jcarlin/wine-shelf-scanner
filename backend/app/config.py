"""
Centralized configuration for the Wine Shelf Scanner backend.

All constants are defined here to avoid scattered magic numbers
and enable easy configuration management.
"""

import os
from pathlib import Path
from typing import List, Optional


class Config:
    """Application configuration constants."""

    # === Confidence Thresholds ===
    # These match the UX rules in CLAUDE.md
    VISIBILITY_THRESHOLD = 0.45       # Show in results (opacity 0.5)
    TAPPABLE_THRESHOLD = 0.65         # Enable detail tap (opacity 0.75)
    HIGH_CONFIDENCE_THRESHOLD = 0.85  # Skip LLM for high-confidence matches (lowered to reduce LLM calls)
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
    PROXIMITY_THRESHOLD = 0.25  # Text must be within this distance of bottle
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
    def debug_mode() -> bool:
        """Always include debug info in scan responses. Default: False."""
        return os.getenv("DEBUG_MODE", "false").lower() == "true"

    # === Vision Cache ===
    @staticmethod
    def vision_cache_enabled() -> bool:
        """Enable Vision API response caching."""
        return os.getenv("VISION_CACHE_ENABLED", "false").lower() == "true"

    @staticmethod
    def vision_cache_ttl_days() -> int:
        """Vision cache TTL in days (0 = no expiry)."""
        try:
            return int(os.getenv("VISION_CACHE_TTL_DAYS", "7"))
        except ValueError:
            return 7

    @staticmethod
    def vision_cache_max_size_mb() -> int:
        """Maximum vision cache size in MB before LRU eviction."""
        try:
            return int(os.getenv("VISION_CACHE_MAX_SIZE_MB", "500"))
        except ValueError:
            return 500

    # === Database Persistence ===
    @staticmethod
    def database_path() -> str:
        """Path to SQLite database file.
        Default: backend/app/data/wines.db (relative to app package).
        Override with DATABASE_PATH env var for container deployments.
        """
        default = str(Path(__file__).parent / "data" / "wines.db")
        return os.getenv("DATABASE_PATH", default)

    @staticmethod
    def gcs_db_bucket() -> str:
        """GCS bucket name for wine database storage."""
        return os.getenv("GCS_DB_BUCKET", "")

    @staticmethod
    def gcs_db_path() -> str:
        """Object path within GCS bucket for wines.db."""
        return os.getenv("GCS_DB_PATH", "data/wines.db")

    # === LLM Rating Cache ===
    @staticmethod
    def use_llm_cache() -> bool:
        """Enable LLM rating cache for discovered wines. Default: True."""
        return os.getenv("USE_LLM_CACHE", "true").lower() == "true"

    # === Vision Fallback ===
    # Max confidence for visual-only identification (never top-3 emphasis)
    VISION_FALLBACK_CONFIDENCE_CAP = 0.70
    # Minimum confidence floor for vision results (ensures tappability)
    VISION_CONFIDENCE_FLOOR = 0.65
    # Default rating when Claude Vision can't estimate (neutral rating)
    VISION_DEFAULT_RATING = 3.5

    @staticmethod
    def use_vision_fallback() -> bool:
        """Enable Claude Vision fallback for unmatched bottles. Default: True."""
        return os.getenv("USE_VISION_FALLBACK", "true").lower() == "true"

    # === Pipeline Mode ===
    @staticmethod
    def pipeline_mode() -> str:
        """Pipeline mode. Default: single_llm (one multimodal LLM call per scan)."""
        return os.getenv("PIPELINE_MODE", "single_llm").lower()

    # === Token Usage Logging ===
    @staticmethod
    def token_usage_log_path() -> str:
        """Path for the per-call token-usage JSONL file.

        Empty string disables the file write (e.g., Cloud Run, where the
        filesystem is ephemeral tmpfs and burns container memory). The
        structured stdout JSON line is still emitted in either case —
        capture it via Cloud Logging in production.
        """
        return os.getenv("TOKEN_USAGE_LOG_PATH", "backend/logs/token_usage.jsonl")

    # === Single-LLM Pipeline ===
    @staticmethod
    def single_llm_model() -> str:
        """Multimodal model for the single-LLM pipeline.

        Any LiteLLM-supported multimodal model works — e.g.:
          - anthropic/claude-sonnet-4-6 (default — strong 2D bbox quality, ~$0.02-0.04/scan)
          - anthropic/claude-opus-4-7 (strongest, ~$0.05-0.07/scan, ~25s latency)
          - anthropic/claude-haiku-4-5-20251001 (NOT recommended — degenerates to
            1D-lane bboxes on dense shelves; see CLAUDE.md "Known limitations")
          - gemini/gemini-2.5-pro
        """
        return os.getenv("SINGLE_LLM_MODEL", "anthropic/claude-sonnet-4-6")

    @staticmethod
    def detect_read_model() -> str:
        """Label-reading model for the detect_read pipeline (set-of-marks +
        crop re-reads; the LLM never emits coordinates)."""
        return os.getenv("DETECT_READ_MODEL", "anthropic/claude-sonnet-5")

    @staticmethod
    def detect_read_min_bottle_px() -> float:
        """Input-quality floor: reject scans whose median detected bottle width
        (full-resolution px) is below this — label text is illegible below
        ~140px, so coverage collapses while cost is still spent
        (FEASIBILITY_VERDICT.md §1 note 3). 0 disables the gate."""
        return float(os.getenv("DETECT_READ_MIN_BOTTLE_PX", "140"))

    # === Abuse Protection (W1) ===
    @staticmethod
    def app_attest_enforce() -> str:
        """Enforcement mode for /scan identity: 'off' (default; dev/tests),
        'log' (admit unattested callers but log + quota them), 'require'
        (401 without a valid App Attest assertion or web proxy secret)."""
        mode = os.getenv("APP_ATTEST_ENFORCE", "off").lower()
        return mode if mode in ("off", "log", "require") else "off"

    @staticmethod
    def app_attest_team_id() -> str:
        """Apple Developer Team ID (empty until the human gate provides it)."""
        return os.getenv("APPLE_TEAM_ID", "")

    @staticmethod
    def app_attest_bundle_id() -> str:
        return os.getenv("APP_BUNDLE_ID", "com.wineshelfscanner.app")

    @staticmethod
    def app_attest_app_id() -> str:
        """App ID as used in the App Attest RP ID hash: TEAMID.bundle.id"""
        return f"{Config.app_attest_team_id()}.{Config.app_attest_bundle_id()}"

    @staticmethod
    def app_attest_allow_development() -> bool:
        """Accept development-environment attestations (sandbox/TestFlight dev)."""
        return os.getenv("APP_ATTEST_ALLOW_DEV", "false").lower() == "true"

    @staticmethod
    def device_daily_scan_limit() -> int:
        """Per-identity daily scan cap (safety, not monetization). 0 disables."""
        return int(os.getenv("DEVICE_DAILY_SCAN_LIMIT", "40"))

    @staticmethod
    def daily_spend_limit_usd() -> float:
        """Global daily-spend circuit breaker; /scan returns 503 above it.
        0 disables."""
        return float(os.getenv("DAILY_SPEND_LIMIT_USD", "25"))

    @staticmethod
    def api_client_secret() -> Optional[str]:
        """Shared secret for server-side web clients (Vercel proxy) that
        cannot do App Attest. None disables the web credential path."""
        return os.getenv("API_CLIENT_SECRET") or None

    # === Fast Pipeline ===
    @staticmethod
    def use_fast_pipeline() -> bool:
        """Use single-pass multimodal LLM pipeline instead of legacy multi-stage. Default: False."""
        return os.getenv("USE_FAST_PIPELINE", "false").lower() == "true"

    @staticmethod
    def fast_pipeline_model() -> str:
        """Multimodal model for fast pipeline. Default: gemini-2.0-flash."""
        return os.getenv("FAST_PIPELINE_MODEL", "gemini-2.0-flash")

    @staticmethod
    def fast_pipeline_timeout() -> float:
        """Timeout in seconds for fast pipeline LLM call. Default: 15.0."""
        try:
            return float(os.getenv("FAST_PIPELINE_TIMEOUT", "15.0"))
        except ValueError:
            return 15.0

    @staticmethod
    def fast_pipeline_fallback() -> bool:
        """Fall back to legacy pipeline if fast pipeline fails. Default: True."""
        return os.getenv("FAST_PIPELINE_FALLBACK", "true").lower() == "true"

    # === Flash Names Pipeline ===
    @staticmethod
    def flash_names_max_tokens() -> int:
        """Max tokens for Flash Names Gemini call. Default: 4096."""
        try:
            return int(os.getenv("FLASH_NAMES_MAX_TOKENS", "4096"))
        except ValueError:
            return 4096

    @staticmethod
    def flash_names_model() -> str:
        """Model override for Flash Names pipeline. Empty string = use fast_pipeline_model()."""
        return os.getenv("FLASH_NAMES_MODEL", "")

    @staticmethod
    def llm_image_max_dim() -> int:
        """Max image dimension for LLM calls. Default: 2048."""
        try:
            return int(os.getenv("LLM_IMAGE_MAX_DIM", "2048"))
        except ValueError:
            return 2048

    @staticmethod
    def llm_image_quality() -> int:
        """JPEG quality for LLM image compression. Default: 85."""
        try:
            return int(os.getenv("LLM_IMAGE_QUALITY", "85"))
        except ValueError:
            return 85

    # === Security ===
    MAX_IMAGE_SIZE_MB = 10
    MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
    ALLOWED_CONTENT_TYPES: List[str] = [
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/heic",
        "image/heif",
        "image/webp",
    ]
