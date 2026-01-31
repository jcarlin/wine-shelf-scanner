"""
OCR text processing: grouping text to bottles and normalization.
"""

import re
from dataclasses import dataclass

from .vision import DetectedObject, TextBlock, BoundingBox


@dataclass
class BottleText:
    """Text grouped to a specific bottle."""
    bottle: DetectedObject
    text_fragments: list[str]
    combined_text: str
    normalized_name: str


class OCRProcessor:
    """Processes OCR results to extract wine names per bottle."""

    # Proximity threshold for assigning text to bottles
    # Text must be within this normalized distance of bottle center
    PROXIMITY_THRESHOLD = 0.15

    # Patterns to remove during normalization
    YEAR_PATTERN = re.compile(r'\b(19|20)\d{2}\b')
    SIZE_PATTERN = re.compile(r'\b\d+\s*(ml|ML|mL|L|l|cl|CL)\b', re.IGNORECASE)
    PRICE_PATTERN = re.compile(r'\$\d+\.?\d*')
    ABV_PATTERN = re.compile(r'\b\d+\.?\d*\s*%\s*(alc|abv|vol)?\b', re.IGNORECASE)

    # Marketing/filler words to remove
    FILLER_WORDS = {
        'reserve', 'special', 'edition', 'limited', 'select', 'premium',
        'estate', 'bottled', 'produced', 'imported', 'product', 'contains',
        'sulfites', 'wine', 'vino', 'vin', 'winery', 'vineyard', 'cellars',
        'vintage', 'aged', 'barrel', 'oak', 'months', 'years'
    }

    def __init__(self, image_width: int = 1000, image_height: int = 1000):
        """
        Initialize processor.

        Args:
            image_width: Image width for normalizing pixel coordinates
            image_height: Image height for normalizing pixel coordinates
        """
        self.image_width = image_width
        self.image_height = image_height

    def process(
        self,
        bottles: list[DetectedObject],
        text_blocks: list[TextBlock]
    ) -> list[BottleText]:
        """
        Group text to bottles and normalize wine names.

        Args:
            bottles: Detected bottle objects with bounding boxes
            text_blocks: OCR text blocks with positions

        Returns:
            List of BottleText with normalized wine names
        """
        results = []

        for bottle in bottles:
            # Find text blocks near this bottle
            nearby_text = self._find_nearby_text(bottle, text_blocks)

            # Combine fragments
            combined = ' '.join(nearby_text)

            # Normalize to canonical wine name
            normalized = self._normalize_text(combined)

            results.append(BottleText(
                bottle=bottle,
                text_fragments=nearby_text,
                combined_text=combined,
                normalized_name=normalized
            ))

        return results

    def _find_nearby_text(
        self,
        bottle: DetectedObject,
        text_blocks: list[TextBlock]
    ) -> list[str]:
        """Find text blocks spatially close to a bottle."""
        nearby = []
        bottle_center = bottle.bbox.center

        for block in text_blocks:
            # Normalize text bbox if needed (Vision API returns pixels)
            text_center = self._get_normalized_center(block.bbox)

            # Calculate distance
            distance = self._distance(bottle_center, text_center)

            # Check if text overlaps or is near bottle bbox
            if distance < self.PROXIMITY_THRESHOLD or self._overlaps(bottle.bbox, block.bbox):
                nearby.append(block.text)

        return nearby

    def _get_normalized_center(self, bbox: BoundingBox) -> tuple[float, float]:
        """Get center point, normalizing pixel coordinates if needed."""
        # If coordinates are > 1, they're pixels - normalize them
        x = bbox.x
        y = bbox.y
        w = bbox.width
        h = bbox.height

        if x > 1 or y > 1:
            x = x / self.image_width
            y = y / self.image_height
            w = w / self.image_width
            h = h / self.image_height

        return (x + w / 2, y + h / 2)

    def _distance(self, p1: tuple[float, float], p2: tuple[float, float]) -> float:
        """Euclidean distance between two points."""
        return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5

    def _overlaps(self, bbox1: BoundingBox, bbox2: BoundingBox) -> bool:
        """Check if two bounding boxes overlap."""
        # Normalize bbox2 if needed
        x2, y2 = bbox2.x, bbox2.y
        w2, h2 = bbox2.width, bbox2.height

        if x2 > 1 or y2 > 1:
            x2 = x2 / self.image_width
            y2 = y2 / self.image_height
            w2 = w2 / self.image_width
            h2 = h2 / self.image_height

        # Check overlap
        return not (
            bbox1.x + bbox1.width < x2 or
            x2 + w2 < bbox1.x or
            bbox1.y + bbox1.height < y2 or
            y2 + h2 < bbox1.y
        )

    def _normalize_text(self, text: str) -> str:
        """
        Normalize OCR text to canonical wine name.

        Removes:
        - Years (2019, 2021, etc.)
        - Sizes (750ml, 1L, etc.)
        - Prices ($24.99)
        - ABV (13.5% alc)
        - Marketing/filler words
        """
        result = text

        # Remove patterns
        result = self.YEAR_PATTERN.sub('', result)
        result = self.SIZE_PATTERN.sub('', result)
        result = self.PRICE_PATTERN.sub('', result)
        result = self.ABV_PATTERN.sub('', result)

        # Remove filler words (case-insensitive)
        words = result.split()
        words = [w for w in words if w.lower() not in self.FILLER_WORDS]
        result = ' '.join(words)

        # Clean up whitespace and punctuation
        result = re.sub(r'\s+', ' ', result)
        result = re.sub(r'[^\w\s\'-]', '', result)
        result = result.strip()

        # Title case for consistency
        if result:
            result = ' '.join(word.capitalize() for word in result.split())

        return result
