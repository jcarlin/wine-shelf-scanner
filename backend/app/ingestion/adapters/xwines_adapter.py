"""
XWines dataset adapter.

Handles the XWines dataset which has ratings and wines in separate files.
Joins them together and yields RawWineRecord objects.
"""

import csv
import hashlib
from pathlib import Path
from typing import Optional, Iterator
from collections import defaultdict

from ..protocols import DataSourceAdapter, RawWineRecord


class XWinesAdapter(DataSourceAdapter):
    """
    Adapter for XWines dataset.

    The XWines dataset has:
    - XWines_Slim_1K_wines.csv: Wine metadata (WineID, WineName, Type, etc.)
    - XWines_Slim_150K_ratings.csv: User ratings (WineID, Rating 1-5)

    This adapter joins them and aggregates ratings per wine.
    """

    def __init__(
        self,
        wines_path: str,
        ratings_path: str,
        min_ratings: int = 3,
    ):
        """
        Initialize adapter.

        Args:
            wines_path: Path to wines CSV
            ratings_path: Path to ratings CSV
            min_ratings: Minimum ratings per wine to include
        """
        self.wines_path = Path(wines_path)
        self.ratings_path = Path(ratings_path)
        self.min_ratings = min_ratings
        self._file_hash: Optional[str] = None

    def get_source_name(self) -> str:
        return "xwines"

    def get_file_hash(self) -> Optional[str]:
        """Hash both files combined."""
        if self._file_hash:
            return self._file_hash

        sha256 = hashlib.sha256()
        for path in [self.wines_path, self.ratings_path]:
            if path.exists():
                with open(path, 'rb') as f:
                    for chunk in iter(lambda: f.read(8192), b''):
                        sha256.update(chunk)

        self._file_hash = sha256.hexdigest()
        return self._file_hash

    def iter_records(self) -> Iterator[RawWineRecord]:
        """Iterate over wine records with aggregated ratings."""
        # Step 1: Load all ratings and aggregate by WineID
        wine_ratings: dict[str, list[float]] = defaultdict(list)

        with open(self.ratings_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                wine_id = row.get('WineID')
                rating_str = row.get('Rating')
                if wine_id and rating_str:
                    try:
                        rating = float(rating_str)
                        if 1.0 <= rating <= 5.0:
                            wine_ratings[wine_id].append(rating)
                    except ValueError:
                        continue

        print(f"  Loaded {sum(len(r) for r in wine_ratings.values()):,} ratings for {len(wine_ratings):,} wines")

        # Step 2: Load wines and yield records
        row_num = 0
        with open(self.wines_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_num += 1
                wine_id = row.get('WineID')
                wine_name = row.get('WineName', '').strip()

                if not wine_id or not wine_name:
                    continue

                ratings = wine_ratings.get(wine_id, [])
                if len(ratings) < self.min_ratings:
                    continue

                # Calculate average rating
                avg_rating = sum(ratings) / len(ratings)

                # Parse wine type
                wine_type = row.get('Type', '').lower()
                if 'red' in wine_type:
                    wine_type = 'red'
                elif 'white' in wine_type:
                    wine_type = 'white'
                elif 'sparkling' in wine_type:
                    wine_type = 'sparkling'
                elif 'rose' in wine_type or 'rosé' in wine_type:
                    wine_type = 'rose'
                else:
                    wine_type = None

                # Parse grapes/varietal
                grapes_str = row.get('Grapes', '')
                varietal = None
                if grapes_str:
                    # Parse ['Grape1', 'Grape2'] format
                    try:
                        grapes = eval(grapes_str) if grapes_str.startswith('[') else [grapes_str]
                        if grapes:
                            varietal = grapes[0].replace('/', ' ')
                    except:
                        pass

                yield RawWineRecord(
                    wine_name=wine_name,
                    rating=round(avg_rating, 2),
                    rating_scale=(1.0, 5.0),  # Vivino-style
                    source_name=self.get_source_name(),
                    winery=row.get('WineryName', '').strip() or None,
                    region=row.get('RegionName', '').strip() or None,
                    country=row.get('Country', '').strip() or None,
                    varietal=varietal,
                    wine_type=wine_type,
                    row_number=row_num,
                )
