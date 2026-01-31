"""
Protocols and data classes for wine ingestion.

Defines the interface that data source adapters must implement.
"""

from dataclasses import dataclass, field
from typing import Protocol, Iterator, Optional


@dataclass
class RawWineRecord:
    """
    A raw wine record from a data source.

    This is the standard intermediate format that all adapters produce.
    The pipeline normalizes and resolves these into canonical wines.
    """
    wine_name: str
    rating: float
    rating_scale: tuple[float, float]  # (min, max) e.g., (80, 100) or (1, 5)
    source_name: str

    # Optional metadata
    winery: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    varietal: Optional[str] = None
    wine_type: Optional[str] = None  # red, white, rose, sparkling
    description: Optional[str] = None

    # For tracking
    row_number: Optional[int] = None

    def __post_init__(self):
        """Validate rating is within scale."""
        min_val, max_val = self.rating_scale
        if not (min_val <= self.rating <= max_val):
            # Clamp to scale bounds
            self.rating = max(min_val, min(max_val, self.rating))


class DataSourceAdapter(Protocol):
    """
    Protocol for data source adapters.

    Each adapter reads from a specific data source format (CSV, API, etc.)
    and yields standardized RawWineRecord objects.
    """

    def iter_records(self) -> Iterator[RawWineRecord]:
        """
        Iterate over wine records from the source.

        Yields:
            RawWineRecord for each valid wine in the source
        """
        ...

    def get_source_name(self) -> str:
        """
        Get the unique identifier for this source.

        Returns:
            Source name (e.g., 'kaggle_wine_reviews', 'vivino')
        """
        ...

    def get_file_hash(self) -> Optional[str]:
        """
        Get hash of the source file for idempotent ingestion.

        Returns:
            SHA256 hash of source file, or None if not file-based
        """
        ...


@dataclass
class IngestionStats:
    """Statistics from an ingestion run."""
    source_name: str
    records_read: int = 0
    records_processed: int = 0
    records_added: int = 0
    records_updated: int = 0
    records_merged: int = 0
    records_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/storage."""
        return {
            "source_name": self.source_name,
            "records_read": self.records_read,
            "records_processed": self.records_processed,
            "records_added": self.records_added,
            "records_updated": self.records_updated,
            "records_merged": self.records_merged,
            "records_skipped": self.records_skipped,
            "error_count": len(self.errors),
        }
