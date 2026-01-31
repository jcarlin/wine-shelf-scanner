"""
Wine name matching against ratings database.
"""

import json
import os
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


@dataclass
class WineMatch:
    """A matched wine from the database."""
    canonical_name: str
    rating: float
    confidence: float  # Match confidence (0-1)
    source: str


class WineMatcher:
    """Fuzzy matches wine names against a ratings database."""

    # Minimum similarity score to consider a match
    MIN_SIMILARITY = 0.6

    def __init__(self, database_path: Optional[str] = None):
        """
        Initialize matcher with ratings database.

        Args:
            database_path: Path to ratings JSON file. Defaults to bundled database.
        """
        if database_path is None:
            database_path = Path(__file__).parent.parent / "data" / "ratings.json"

        self.database = self._load_database(database_path)
        self._build_index()

    def _load_database(self, path) -> dict:
        """Load ratings database from JSON file."""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            # Return empty database if file doesn't exist
            return {"wines": []}

    def _build_index(self):
        """Build lookup index for faster matching."""
        self.name_to_wine = {}
        self.all_names = []

        for wine in self.database.get("wines", []):
            canonical = wine["canonical_name"].lower()
            self.name_to_wine[canonical] = wine
            self.all_names.append(canonical)

            # Index aliases too
            for alias in wine.get("aliases", []):
                alias_lower = alias.lower()
                self.name_to_wine[alias_lower] = wine
                self.all_names.append(alias_lower)

    def match(self, query: str) -> Optional[WineMatch]:
        """
        Find best matching wine for a query string.

        Args:
            query: Normalized wine name from OCR

        Returns:
            WineMatch if found, None otherwise
        """
        if not query:
            return None

        query_lower = query.lower()

        # Try exact match first
        if query_lower in self.name_to_wine:
            wine = self.name_to_wine[query_lower]
            return WineMatch(
                canonical_name=wine["canonical_name"],
                rating=wine["rating"],
                confidence=1.0,
                source=wine.get("source", "unknown")
            )

        # Fuzzy match
        best_match = None
        best_score = 0

        for name in self.all_names:
            score = self._similarity(query_lower, name)
            if score > best_score and score >= self.MIN_SIMILARITY:
                best_score = score
                best_match = self.name_to_wine[name]

        if best_match:
            return WineMatch(
                canonical_name=best_match["canonical_name"],
                rating=best_match["rating"],
                confidence=best_score,
                source=best_match.get("source", "unknown")
            )

        return None

    def _similarity(self, s1: str, s2: str) -> float:
        """Calculate similarity between two strings."""
        # Use SequenceMatcher for fuzzy matching
        return SequenceMatcher(None, s1, s2).ratio()

    def match_many(self, queries: list[str]) -> list[Optional[WineMatch]]:
        """Match multiple queries."""
        return [self.match(q) for q in queries]
