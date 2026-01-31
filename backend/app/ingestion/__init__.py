"""
Wine data ingestion package.

Provides a modular pipeline for ingesting wine data from various sources
into the SQLite database with proper normalization and deduplication.
"""

from .protocols import DataSourceAdapter, RawWineRecord
from .normalizers import RatingNormalizer
from .entities import WineEntityResolver, CanonicalWine
from .pipeline import IngestionPipeline

__all__ = [
    "DataSourceAdapter",
    "RawWineRecord",
    "RatingNormalizer",
    "WineEntityResolver",
    "CanonicalWine",
    "IngestionPipeline",
]
