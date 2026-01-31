"""
Rating normalization for wine data ingestion.

Converts ratings from various scales to a unified 1-5 scale using
tier-aligned mapping (not simple linear interpolation).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class RatingConfig:
    """Configuration for a rating scale."""
    scale_min: float
    scale_max: float
    # Tier boundaries (from original scale)
    tier_boundaries: list[tuple[float, float, float, float]]  # (orig_min, orig_max, target_min, target_max)


class RatingNormalizer:
    """
    Normalizes ratings from various scales to 1-5.

    Uses tier-aligned mapping based on wine rating standards:
    - Wine Enthusiast/Wine Spectator: 80-100 scale
    - Vivino: 1-5 scale (passthrough)

    Tier mappings (Wine Enthusiast example):
    - 95-100 ("Classic") → 4.5-5.0
    - 90-94 ("Outstanding") → 4.0-4.5
    - 85-89 ("Very Good") → 3.5-4.0
    - 80-84 ("Good") → 3.0-3.5
    """

    # Pre-defined rating configs
    CONFIGS = {
        # Wine Enthusiast / Wine Spectator (80-100)
        "wine_enthusiast": RatingConfig(
            scale_min=80,
            scale_max=100,
            tier_boundaries=[
                (95, 100, 4.5, 5.0),   # Classic
                (90, 94, 4.0, 4.5),    # Outstanding
                (85, 89, 3.5, 4.0),    # Very Good
                (80, 84, 3.0, 3.5),    # Good
            ]
        ),
        # Vivino (1-5) - passthrough
        "vivino": RatingConfig(
            scale_min=1,
            scale_max=5,
            tier_boundaries=[
                (1, 5, 1, 5),  # Direct mapping
            ]
        ),
        # Generic 100-point
        "100_point": RatingConfig(
            scale_min=0,
            scale_max=100,
            tier_boundaries=[
                (95, 100, 4.5, 5.0),
                (90, 94, 4.0, 4.5),
                (85, 89, 3.5, 4.0),
                (80, 84, 3.0, 3.5),
                (70, 79, 2.5, 3.0),
                (60, 69, 2.0, 2.5),
                (0, 59, 1.0, 2.0),
            ]
        ),
    }

    def __init__(self, default_config: str = "wine_enthusiast"):
        """
        Initialize normalizer.

        Args:
            default_config: Name of default rating config to use
        """
        self.default_config_name = default_config
        self._custom_configs: dict[str, RatingConfig] = {}

    def add_config(self, name: str, config: RatingConfig):
        """Add a custom rating configuration."""
        self._custom_configs[name] = config

    def get_config(self, name: str) -> Optional[RatingConfig]:
        """Get config by name."""
        return self._custom_configs.get(name) or self.CONFIGS.get(name)

    def normalize(
        self,
        rating: float,
        scale: tuple[float, float],
        config_name: Optional[str] = None
    ) -> float:
        """
        Normalize a rating to the 1-5 scale.

        Args:
            rating: Original rating value
            scale: (min, max) of original scale
            config_name: Optional config name (auto-detected if not provided)

        Returns:
            Normalized rating on 1-5 scale
        """
        scale_min, scale_max = scale

        # Auto-detect config based on scale
        if config_name is None:
            config_name = self._detect_config(scale_min, scale_max)

        config = self.get_config(config_name)
        if config is None:
            # Fall back to linear interpolation
            return self._linear_normalize(rating, scale_min, scale_max)

        # Apply tier-based mapping
        return self._tier_normalize(rating, config)

    def _detect_config(self, scale_min: float, scale_max: float) -> str:
        """Auto-detect rating config based on scale bounds."""
        if scale_min == 80 and scale_max == 100:
            return "wine_enthusiast"
        elif scale_min == 1 and scale_max == 5:
            return "vivino"
        elif scale_min == 0 and scale_max == 100:
            return "100_point"
        else:
            return self.default_config_name

    def _tier_normalize(self, rating: float, config: RatingConfig) -> float:
        """Apply tier-based normalization."""
        for orig_min, orig_max, target_min, target_max in config.tier_boundaries:
            if orig_min <= rating <= orig_max:
                # Linear interpolation within tier
                if orig_max == orig_min:
                    return target_min
                ratio = (rating - orig_min) / (orig_max - orig_min)
                return target_min + ratio * (target_max - target_min)

        # Rating outside all tiers - use linear interpolation
        return self._linear_normalize(rating, config.scale_min, config.scale_max)

    def _linear_normalize(
        self,
        rating: float,
        scale_min: float,
        scale_max: float,
        target_min: float = 1.0,
        target_max: float = 5.0
    ) -> float:
        """Simple linear normalization as fallback."""
        if scale_max == scale_min:
            return target_min

        ratio = (rating - scale_min) / (scale_max - scale_min)
        normalized = target_min + ratio * (target_max - target_min)

        # Clamp to target range
        return max(target_min, min(target_max, normalized))

    def normalize_batch(
        self,
        ratings: list[tuple[float, tuple[float, float]]],
        config_name: Optional[str] = None
    ) -> list[float]:
        """
        Normalize a batch of ratings.

        Args:
            ratings: List of (rating, scale) tuples
            config_name: Optional config name

        Returns:
            List of normalized ratings
        """
        return [
            self.normalize(rating, scale, config_name)
            for rating, scale in ratings
        ]
