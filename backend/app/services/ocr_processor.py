"""
OCR text processing: grouping text to bottles and normalization.
"""

import re
from dataclasses import dataclass

from ..config import Config
from .vision import BoundingBox, DetectedObject, TextBlock


# Patterns for filtering non-wine text
_YEAR_PATTERN = re.compile(r'\b(19|20)\d{2}\b')
_SIZE_PATTERN = re.compile(r'\b\d+\s*(ml|ML|mL|L|l|cl|CL)\b', re.IGNORECASE)
_PRICE_PATTERN = re.compile(r'[\$€£]\d+\.?\d*|\d+[.,]\d{2}\s*(руб|₽|р)?', re.IGNORECASE)
_ABV_PATTERN = re.compile(r'\b\d+\.?\d*\s*%\s*(alc|abv|vol)?\b', re.IGNORECASE)
_CYRILLIC_PATTERN = re.compile(r'[а-яА-ЯёЁ]+')
_NUMERIC_ONLY_PATTERN = re.compile(r'^\d+$')
_SHORT_TEXT_PATTERN = re.compile(r'^.{1,2}$')

# Known wine name indicators (brands, regions, varietals)
_WINE_INDICATORS = {
    # Varietals
    'cabernet', 'sauvignon', 'merlot', 'pinot', 'noir', 'grigio', 'chardonnay',
    'riesling', 'syrah', 'shiraz', 'tempranillo', 'malbec', 'zinfandel',
    'sangiovese', 'nebbiolo', 'grenache', 'mourvedre', 'viognier', 'verdejo',
    'albarino', 'garnacha', 'monastrell', 'rioja', 'crianza', 'reserva',
    # Common brand patterns
    'chateau', 'château', 'domaine', 'bodega', 'cantina', 'tenuta', 'casa',
    'torre', 'campo', 'monte', 'villa', 'vina', 'viña',
}

# Words that indicate this is NOT a wine name
_NON_WINE_WORDS = {
    'contains', 'sulfites', 'product', 'imported', 'bottled', 'produced',
    'government', 'warning', 'surgeon', 'general', 'health', 'pregnant',
    'women', 'alcohol', 'drinking', 'impairs', 'ability', 'drive',
    'operate', 'machinery', 'consumption', 'cause', 'problems',
    'distributed', 'shipped', 'ounces', 'milliliters', 'liters',
}


def extract_wine_names(raw_text: str) -> list[str]:
    """
    Extract wine names from raw OCR text.

    Args:
        raw_text: Raw OCR text from Vision API

    Returns:
        List of cleaned wine names
    """
    if not raw_text:
        return []

    lines = raw_text.split('\n')
    wine_names = []
    seen = set()  # Dedupe

    for line in lines:
        cleaned = _clean_line(line)
        if cleaned and _looks_like_wine_name(cleaned):
            # Normalize for deduplication
            key = cleaned.lower()
            if key not in seen:
                seen.add(key)
                wine_names.append(cleaned)

    return wine_names


def _clean_line(line: str) -> str:
    """Clean a single line of OCR text."""
    result = line.strip()

    # Remove patterns
    result = _YEAR_PATTERN.sub('', result)
    result = _SIZE_PATTERN.sub('', result)
    result = _PRICE_PATTERN.sub('', result)
    result = _ABV_PATTERN.sub('', result)
    result = _CYRILLIC_PATTERN.sub('', result)  # Remove Russian text

    # Clean up whitespace and some punctuation
    result = re.sub(r'\s+', ' ', result)
    result = result.strip()

    return result


def _looks_like_wine_name(text: str) -> bool:
    """Check if text looks like a wine name."""
    # Too short
    if len(text) < 3:
        return False

    # Numeric only
    if _NUMERIC_ONLY_PATTERN.match(text):
        return False

    # Contains non-wine warning text
    text_lower = text.lower()
    for word in _NON_WINE_WORDS:
        if word in text_lower:
            return False

    # Check for wine indicators (positive signal)
    has_indicator = any(ind in text_lower for ind in _WINE_INDICATORS)

    # If it has a wine indicator, accept it
    if has_indicator:
        return True

    # Otherwise, accept if it looks like a brand name:
    # - Starts with capital letter
    # - Contains only letters, spaces, apostrophes, hyphens
    # - Is reasonable length (3-50 chars)
    if not text[0].isupper():
        return False

    if len(text) > 50:
        return False

    # Allow letters, spaces, apostrophes, hyphens, periods
    if not re.match(r"^[A-Za-z\s'\-\.]+$", text):
        return False

    return True


@dataclass
class BottleText:
    """Text grouped to a specific bottle."""
    bottle: DetectedObject
    text_fragments: list[str]
    combined_text: str
    normalized_name: str


class OCRProcessor:
    """Processes OCR results to extract wine names per bottle."""

    # Patterns to remove during normalization (reuse module-level patterns)
    YEAR_PATTERN = _YEAR_PATTERN
    SIZE_PATTERN = _SIZE_PATTERN
    PRICE_PATTERN = _PRICE_PATTERN
    ABV_PATTERN = _ABV_PATTERN

    # Marketing/filler words to remove
    FILLER_WORDS = {
        'reserve', 'special', 'edition', 'limited', 'select', 'premium',
        'estate', 'bottled', 'produced', 'imported', 'product', 'contains',
        'sulfites', 'wine', 'vino', 'vin', 'winery', 'vineyard', 'cellars',
        'vintage', 'aged', 'barrel', 'oak', 'months', 'years',
        # Region names that appear on labels but shouldn't be in wine name
        'napa', 'sonoma', 'lodi', 'paso', 'robles', 'california', 'oregon',
        'washington', 'mendocino', 'monterey', 'valley', 'county', 'coast',
        'central', 'north', 'south', 'eastern', 'western', 'appellation',
        # French generic terms (not specific appellations - keep village names!)
        'bourgogne', 'burgundy', 'loire', 'rhone', 'alsace',
        'provence', 'languedoc', 'roussillon', 'grand', 'cru',
        'premier', 'appellation', 'controlee', 'contrôlée', 'origine', 'protegee',
        'côtes', 'cotes', 'haut',
        # Italian terms
        'toscana', 'tuscany', 'piemonte', 'piedmont', 'veneto', 'sicilia',
        'docg', 'doc', 'igt', 'classico', 'superiore', 'riserva',
        # Spanish terms
        'rioja', 'ribera', 'duero', 'priorat', 'rueda', 'denominacion',
        'crianza', 'reserva', 'gran',
        # Australian regions
        'barossa', 'mclaren', 'vale', 'hunter', 'clare', 'margaret', 'river',
        # Common label words to remove
        'vinted', 'grown', 'made', 'crafted', 'selected', 'from', 'the',
        'and', 'for', 'with', 'our', 'this', 'that', 'by', 'of', 'in',
        # Label boilerplate
        'mis', 'en', 'bouteille', 'par', 'a', 'au', 'negociant', 'négociant',
        'eleveur', 'éleveur', 'producteur', 'recoltant', 'récoltant', 'produit',
        'product', 'produce', 'produced', 'france', 'french', 'côte', 'cote', 'd',
        'or', 'beaune', 'alsace', 'loire',
        # Generic wine terms that appear on many labels (not wine names)
        'grand', 'vin', 'rouge', 'blanc', 'rose', 'rosé', 'sec', 'demi-sec', 'brut',
        'extra', 'methode', 'méthode', 'traditionnelle', 'traditionnel', 'naturel',
        'millesime', 'millésime', 'millesimé', 'mis', 'bouteille', 'au', 'domaine',
        'mousseux', 'petillant', 'pétillant', 'cremant', 'crémant', 'cava',
        'spumante', 'prosecco', 'franciacorta', 'sparkling',
        # French connectors
        'de', 'du', 'des', 'le', 'la', 'les', 'et', 'en', 'sur',
        # Additional generic terms
        'qualité', 'qualite', 'quality', 'superieur', 'supérieur', 'cuvee', 'cuvée',
        'chateau', 'château', 'vieilles', 'vignes', 'terroir', 'aoc', 'aop',
    }

    def __init__(
        self,
        image_width: int = Config.DEFAULT_IMAGE_WIDTH,
        image_height: int = Config.DEFAULT_IMAGE_HEIGHT
    ):
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
            if distance < Config.PROXIMITY_THRESHOLD or self._overlaps(bottle.bbox, block.bbox):
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

        # Deduplicate: keep only first occurrence of each word (case-insensitive)
        seen = set()
        deduped = []
        for w in words:
            w_lower = w.lower()
            # Skip single characters, punctuation-only, and numbers
            if len(w) <= 1 or w_lower in ('-', '--', "'", "d'or", "d'or") or w.isdigit():
                continue
            if w_lower not in seen:
                seen.add(w_lower)
                deduped.append(w)
        words = deduped

        result = ' '.join(words)

        # Clean up whitespace and punctuation
        result = re.sub(r'\s+', ' ', result)
        result = re.sub(r'[^\w\s\'-]', '', result)
        result = result.strip()

        # Title case for consistency
        if result:
            result = ' '.join(word.capitalize() for word in result.split())

        return result
