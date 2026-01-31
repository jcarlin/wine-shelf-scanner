"""
Config-driven CSV adapter for wine data ingestion.

Uses YAML configuration to map CSV columns to RawWineRecord fields.
"""

import csv
import hashlib
import re
from pathlib import Path
from typing import Optional, Iterator

import yaml

from ..protocols import DataSourceAdapter, RawWineRecord


class ConfigDrivenCSVAdapter(DataSourceAdapter):
    """
    CSV adapter configured via YAML.

    Config structure:
    ```yaml
    source_name: kaggle_wine_reviews
    file_path: raw-data/winemag-data_first150k.csv
    rating_scale: [80, 100]
    encoding: utf-8

    column_mapping:
      wine_name: title
      rating: points
      winery: winery
      region: region_1
      country: country
      varietal: variety

    transformations:
      wine_name:
        - strip_whitespace
        - remove_vintage_suffix
    ```
    """

    # Available transformations
    TRANSFORMATIONS = {
        "strip_whitespace": lambda x: x.strip() if x else x,
        "remove_vintage_suffix": lambda x: re.sub(r'\s*\b(19|20)\d{2}\b\s*$', '', x) if x else x,
        "remove_vintage_prefix": lambda x: re.sub(r'^\s*(19|20)\d{2}\s+', '', x) if x else x,
        "remove_vintage_anywhere": lambda x: re.sub(r'\b(19|20)\d{2}\b', '', x) if x else x,
        "title_case": lambda x: x.title() if x else x,
        "lowercase": lambda x: x.lower() if x else x,
    }

    def __init__(self, config_path: str, base_path: Optional[str] = None):
        """
        Initialize adapter from YAML config.

        Args:
            config_path: Path to YAML config file
            base_path: Base path for resolving relative file paths (defaults to cwd)
        """
        self.config_path = Path(config_path)
        self.base_path = Path(base_path) if base_path else Path.cwd()

        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        self._validate_config()
        self._file_hash: Optional[str] = None

    def _validate_config(self):
        """Validate required config fields."""
        required = ["source_name", "file_path", "rating_scale", "column_mapping"]
        for field in required:
            if field not in self.config:
                raise ValueError(f"Missing required config field: {field}")

        required_columns = ["wine_name", "rating"]
        for col in required_columns:
            if col not in self.config["column_mapping"]:
                raise ValueError(f"Missing required column mapping: {col}")

    def get_source_name(self) -> str:
        """Get source name from config."""
        return self.config["source_name"]

    def get_file_hash(self) -> Optional[str]:
        """Calculate SHA256 hash of CSV file."""
        if self._file_hash:
            return self._file_hash

        file_path = self._resolve_path(self.config["file_path"])
        if not file_path.exists():
            return None

        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)

        self._file_hash = sha256.hexdigest()
        return self._file_hash

    def iter_records(self) -> Iterator[RawWineRecord]:
        """Iterate over wine records from CSV."""
        file_path = self._resolve_path(self.config["file_path"])
        encoding = self.config.get("encoding", "utf-8")
        rating_scale = tuple(self.config["rating_scale"])
        column_map = self.config["column_mapping"]
        transformations = self.config.get("transformations", {})

        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                try:
                    record = self._row_to_record(
                        row, row_num, rating_scale, column_map, transformations
                    )
                    if record:
                        yield record
                except Exception as e:
                    # Skip invalid rows
                    continue

    def _row_to_record(
        self,
        row: dict,
        row_num: int,
        rating_scale: tuple[float, float],
        column_map: dict,
        transformations: dict,
    ) -> Optional[RawWineRecord]:
        """Convert a CSV row to RawWineRecord."""
        # Get required fields
        wine_name = self._get_value(row, column_map["wine_name"])
        rating_str = self._get_value(row, column_map["rating"])

        if not wine_name or not rating_str:
            return None

        # Parse rating
        try:
            rating = float(rating_str)
        except ValueError:
            return None

        # Skip ratings outside scale (likely invalid)
        scale_min, scale_max = rating_scale
        if rating < scale_min or rating > scale_max:
            return None

        # Apply transformations
        wine_name = self._apply_transforms(wine_name, transformations.get("wine_name", []))

        # Skip if wine name is too short after transforms
        if not wine_name or len(wine_name) < 3:
            return None

        # Get optional fields
        winery = self._get_value(row, column_map.get("winery"))
        region = self._get_value(row, column_map.get("region"))
        country = self._get_value(row, column_map.get("country"))
        varietal = self._get_value(row, column_map.get("varietal"))
        wine_type = self._get_value(row, column_map.get("wine_type"))
        description = self._get_value(row, column_map.get("description"))

        # Apply transforms to other fields
        if winery:
            winery = self._apply_transforms(winery, transformations.get("winery", ["strip_whitespace"]))
        if region:
            region = self._apply_transforms(region, transformations.get("region", ["strip_whitespace"]))

        return RawWineRecord(
            wine_name=wine_name,
            rating=rating,
            rating_scale=rating_scale,
            source_name=self.get_source_name(),
            winery=winery,
            region=region,
            country=country,
            varietal=varietal,
            wine_type=wine_type,
            description=description,
            row_number=row_num,
        )

    def _get_value(self, row: dict, column_spec: Optional[str]) -> Optional[str]:
        """
        Get value from row by column spec.

        Supports:
        - Simple column name: "winery"
        - Compound columns: "winery+designation" (concatenates with space)
        - Fallback: "winery+designation|winery+variety" (tries first, falls back to second)
        """
        if not column_spec:
            return None

        # Handle fallback (pipe separated)
        if '|' in column_spec:
            for spec in column_spec.split('|'):
                value = self._get_value(row, spec.strip())
                if value:
                    return value
            return None

        # Handle compound (plus separated)
        if '+' in column_spec:
            parts = []
            for col in column_spec.split('+'):
                col = col.strip()
                val = row.get(col)
                if val and isinstance(val, str) and val.strip():
                    parts.append(val.strip())
            return ' '.join(parts) if parts else None

        # Simple column name
        value = row.get(column_spec)
        if value and isinstance(value, str):
            value = value.strip()
            return value if value else None
        return None

    def _apply_transforms(self, value: str, transforms: list[str]) -> str:
        """Apply a list of transformations to a value."""
        for transform_name in transforms:
            if transform_name in self.TRANSFORMATIONS:
                value = self.TRANSFORMATIONS[transform_name](value)
        return value

    def _resolve_path(self, path_str: str) -> Path:
        """Resolve path relative to base_path."""
        path = Path(path_str)
        if path.is_absolute():
            return path
        return self.base_path / path
