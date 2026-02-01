"""
Vivino Global adapter for multi-file wine data ingestion.

Handles multiple CSV files scraped from Vivino's API across different countries.
"""

import csv
import hashlib
import re
from pathlib import Path
from typing import Iterator, Optional

from ..protocols import DataSourceAdapter, RawWineRecord


class VivinoGlobalAdapter(DataSourceAdapter):
    """
    Adapter for ingesting scraped Vivino data from multiple CSV files.

    Reads all vivino_*.csv files from a directory and yields RawWineRecord
    objects for each wine.
    """

    WINE_TYPE_MAP = {
        "red": "red",
        "white": "white",
        "rose": "rose",
        "rosé": "rose",
        "sparkling": "sparkling",
    }

    def __init__(
        self,
        data_dir: str,
        min_reviews: int = 10,
        rating_scale: tuple[float, float] = (1.0, 5.0),
    ):
        """
        Initialize adapter.

        Args:
            data_dir: Directory containing vivino_*.csv files
            min_reviews: Minimum number of reviews required
            rating_scale: Rating scale tuple (min, max)
        """
        self.data_dir = Path(data_dir)
        self.min_reviews = min_reviews
        self.rating_scale = rating_scale
        self._file_hash: Optional[str] = None

    def get_source_name(self) -> str:
        """Get source name."""
        return "vivino_global"

    def get_file_hash(self) -> Optional[str]:
        """Calculate combined hash of all CSV files."""
        if self._file_hash:
            return self._file_hash

        csv_files = sorted(self.data_dir.glob("vivino_*.csv"))
        if not csv_files:
            return None

        # Combine hashes of all files
        combined_hash = hashlib.sha256()
        for csv_file in csv_files:
            sha256 = hashlib.sha256()
            with open(csv_file, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)
            combined_hash.update(sha256.hexdigest().encode())

        self._file_hash = combined_hash.hexdigest()
        return self._file_hash

    def iter_records(self) -> Iterator[RawWineRecord]:
        """Iterate over wine records from all CSV files."""
        csv_files = sorted(self.data_dir.glob("vivino_*.csv"))

        if not csv_files:
            print(f"No vivino_*.csv files found in {self.data_dir}")
            return

        seen_wine_ids = set()  # Track Wine IDs to avoid duplicates

        for csv_file in csv_files:
            print(f"  Processing: {csv_file.name}")
            yield from self._process_file(csv_file, seen_wine_ids)

    def _process_file(
        self,
        csv_file: Path,
        seen_wine_ids: set,
    ) -> Iterator[RawWineRecord]:
        """Process a single CSV file."""
        with open(csv_file, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, start=2):
                try:
                    record = self._row_to_record(row, row_num, seen_wine_ids)
                    if record:
                        yield record
                except Exception:
                    continue

    def _row_to_record(
        self,
        row: dict,
        row_num: int,
        seen_wine_ids: set,
    ) -> Optional[RawWineRecord]:
        """Convert a CSV row to RawWineRecord."""
        # Get required fields
        wine_id = row.get("Wine ID", "")
        winery = row.get("Winery", "")
        wine = row.get("Wine", "")
        rating_str = row.get("Rating", "")
        num_reviews_str = row.get("num_review", "")

        # Skip duplicates by Wine ID
        if wine_id and wine_id in seen_wine_ids:
            return None
        if wine_id:
            seen_wine_ids.add(wine_id)

        # Skip if missing required data
        if not wine or not rating_str:
            return None

        # Parse rating
        try:
            rating = float(rating_str)
        except ValueError:
            return None

        # Parse number of reviews
        try:
            num_reviews = int(float(num_reviews_str)) if num_reviews_str else 0
        except ValueError:
            num_reviews = 0

        # Skip wines with too few reviews
        if num_reviews < self.min_reviews:
            return None

        # Skip invalid ratings
        scale_min, scale_max = self.rating_scale
        if rating < scale_min or rating > scale_max:
            return None

        # Construct wine name
        wine_name = f"{winery} {wine}".strip() if winery else wine
        wine_name = self._clean_wine_name(wine_name)

        if not wine_name or len(wine_name) < 3:
            return None

        # Get optional fields
        region = row.get("Region", "")
        country = row.get("Country", "")
        wine_type_raw = row.get("Wine Type", "")

        # Normalize wine type
        wine_type = self._normalize_wine_type(wine_type_raw)

        return RawWineRecord(
            wine_name=wine_name,
            rating=rating,
            rating_scale=self.rating_scale,
            source_name=self.get_source_name(),
            winery=winery if winery else None,
            region=region if region else None,
            country=country if country else None,
            wine_type=wine_type,
            row_number=row_num,
        )

    def _clean_wine_name(self, name: str) -> str:
        """Clean wine name by removing vintage years and extra whitespace."""
        # Remove vintage year suffixes like "2019", "2020"
        name = re.sub(r'\s*\b(19|20)\d{2}\b\s*$', '', name)
        # Remove duplicate whitespace
        name = re.sub(r'\s+', ' ', name)
        return name.strip()

    def _normalize_wine_type(self, wine_type: str) -> Optional[str]:
        """Normalize wine type to standard values."""
        if not wine_type:
            return None

        normalized = wine_type.lower().strip()
        return self.WINE_TYPE_MAP.get(normalized)
