"""
Tiered wine recognition pipeline.

Architecture:
1. Vision API → TEXT_DETECTION + OBJECT_LOCALIZATION
2. Text clustering → Group OCR fragments by bottle
3. Enhanced fuzzy matching → Try database match first
4. LLM fallback → For low-confidence/unknown wines
"""

from dataclasses import dataclass
from typing import Optional

from .wine_matcher import WineMatcher, WineMatch
from .llm_normalizer import NormalizerProtocol, get_normalizer, NormalizationResult
from .ocr_processor import BottleText


@dataclass
class RecognizedWine:
    """A recognized wine from the pipeline."""
    wine_name: str
    rating: Optional[float]  # None if not in database
    confidence: float
    source: str              # 'database' or 'llm'
    identified: bool         # True = show checkmark
    bottle_text: BottleText  # Original bottle context


class RecognitionPipeline:
    """
    Tiered recognition pipeline for wine labels.

    Flow:
    1. Try enhanced fuzzy match against database
    2. If confidence < threshold, use LLM to normalize
    3. Try fuzzy match again with normalized name
    4. If still no DB match but LLM says is_wine → return as identified (no rating)
    """

    # Confidence threshold for accepting fuzzy match without LLM
    FUZZY_CONFIDENCE_THRESHOLD = 0.7

    # Minimum confidence for fallback list
    FALLBACK_THRESHOLD = 0.45

    def __init__(
        self,
        wine_matcher: Optional[WineMatcher] = None,
        normalizer: Optional[NormalizerProtocol] = None,
        use_llm: bool = True
    ):
        """
        Initialize pipeline.

        Args:
            wine_matcher: WineMatcher instance (default: creates new)
            normalizer: LLM normalizer (default: Claude Haiku)
            use_llm: Whether to use LLM fallback (disable for testing)
        """
        self.wine_matcher = wine_matcher or WineMatcher()
        self.normalizer = normalizer or get_normalizer(use_mock=not use_llm)
        self.use_llm = use_llm

    async def recognize(
        self,
        bottle_texts: list[BottleText]
    ) -> list[RecognizedWine]:
        """
        Recognize wines from bottle text clusters.

        Args:
            bottle_texts: List of BottleText from OCR processor

        Returns:
            List of RecognizedWine with ratings where available
        """
        results = []

        for bt in bottle_texts:
            result = await self._recognize_single(bt)
            if result:
                results.append(result)

        return results

    async def _recognize_single(
        self,
        bottle_text: BottleText
    ) -> Optional[RecognizedWine]:
        """Recognize a single bottle."""
        # Skip if no meaningful text
        if not bottle_text.normalized_name or len(bottle_text.normalized_name) < 3:
            return None

        # Step 1: Try enhanced fuzzy match
        match = self.wine_matcher.match(bottle_text.normalized_name)

        if match and match.confidence >= self.FUZZY_CONFIDENCE_THRESHOLD:
            # High-confidence DB match
            return RecognizedWine(
                wine_name=match.canonical_name,
                rating=match.rating,
                confidence=min(bottle_text.bottle.confidence, match.confidence),
                source="database",
                identified=True,
                bottle_text=bottle_text
            )

        # Step 2: LLM fallback for low-confidence/no match
        if self.use_llm:
            llm_result = await self._try_llm_normalization(bottle_text, match)
            if llm_result:
                return llm_result

        # Step 3: Return low-confidence DB match if we have one
        if match and match.confidence >= self.FALLBACK_THRESHOLD:
            return RecognizedWine(
                wine_name=match.canonical_name,
                rating=match.rating,
                confidence=match.confidence,
                source="database",
                identified=True,
                bottle_text=bottle_text
            )

        return None

    async def _try_llm_normalization(
        self,
        bottle_text: BottleText,
        existing_match: Optional[WineMatch]
    ) -> Optional[RecognizedWine]:
        """Try LLM normalization and re-match."""
        # Use combined text for better context
        text_for_llm = bottle_text.combined_text or bottle_text.normalized_name

        context = {
            "bottle_confidence": bottle_text.bottle.confidence,
            "text_fragments": bottle_text.text_fragments[:5]  # Limit for cost
        }

        llm_result = await self.normalizer.normalize(text_for_llm, context)

        if not llm_result.is_wine:
            return None

        # Try matching the LLM-normalized name
        if llm_result.wine_name:
            match = self.wine_matcher.match(llm_result.wine_name)

            if match and match.confidence >= self.FALLBACK_THRESHOLD:
                # LLM helped us find a DB match
                return RecognizedWine(
                    wine_name=match.canonical_name,
                    rating=match.rating,
                    confidence=min(llm_result.confidence, match.confidence),
                    source="database",
                    identified=True,
                    bottle_text=bottle_text
                )

            # LLM identified wine but not in DB → show checkmark, no rating
            if llm_result.confidence >= 0.6:
                return RecognizedWine(
                    wine_name=llm_result.wine_name,
                    rating=None,
                    confidence=llm_result.confidence,
                    source="llm",
                    identified=True,
                    bottle_text=bottle_text
                )

        return None
