"""
Tiered wine recognition pipeline.

Architecture:
1. Vision API → TEXT_DETECTION + OBJECT_LOCALIZATION
2. Text clustering → Group OCR fragments by bottle
3. Enhanced fuzzy matching → Try database match first
4. LLM fallback → For low-confidence/unknown wines (batched for performance)

Performance optimizations:
- High-confidence fuzzy matches (≥0.85) skip LLM entirely
- Lower-confidence matches are validated in a single batched LLM call
- Expected latency: 6000ms → 800-1000ms for 8 bottles
"""

from dataclasses import dataclass
from typing import Optional

from ..config import Config
from ..models.debug import (
    DebugPipelineStep,
    FuzzyMatchDebug,
    FuzzyMatchScores,
    LLMValidationDebug,
)
from .llm_normalizer import (
    NormalizerProtocol,
    BatchValidationItem,
    BatchValidationResult,
    get_normalizer,
)
from .ocr_processor import BottleText
from .wine_matcher import WineMatcher, WineMatch, WineMatchWithScores


class DebugCollector:
    """
    Collects debug information when enabled, no-ops when disabled.

    This class extracts the debug concern from RecognitionPipeline,
    providing a clean interface that handles the enabled/disabled
    state internally.
    """

    def __init__(self, enabled: bool = False):
        """
        Initialize collector.

        Args:
            enabled: If True, collect debug info. If False, all methods are no-ops.
        """
        self.enabled = enabled
        self.steps: list[DebugPipelineStep] = []

    def reset(self) -> None:
        """Reset collected debug info for a new recognition run."""
        self.steps = []

    def add_step(
        self,
        bottle_text: "BottleText",
        bottle_idx: int,
        match_with_scores: Optional["WineMatchWithScores"],
        llm_debug: Optional[LLMValidationDebug],
        result: Optional["RecognizedWine"],
        step_failed: Optional[str],
        included: bool
    ) -> None:
        """Add a debug step to the collection. No-op if disabled."""
        if not self.enabled:
            return

        fuzzy_debug = None
        if match_with_scores:
            fuzzy_debug = FuzzyMatchDebug(
                candidate=match_with_scores.canonical_name,
                scores=FuzzyMatchScores(
                    ratio=match_with_scores.scores.ratio,
                    partial_ratio=match_with_scores.scores.partial_ratio,
                    token_sort_ratio=match_with_scores.scores.token_sort_ratio,
                    phonetic_bonus=match_with_scores.scores.phonetic_bonus,
                    weighted_score=match_with_scores.scores.weighted_score
                ),
                rating=match_with_scores.rating
            )

        final_result = None
        if result:
            final_result = {
                "wine_name": result.wine_name,
                "confidence": result.confidence,
                "source": result.source
            }

        self.steps.append(DebugPipelineStep(
            raw_text=bottle_text.combined_text or "",
            normalized_text=bottle_text.normalized_name or "",
            bottle_index=bottle_idx,
            fuzzy_match=fuzzy_debug,
            llm_validation=llm_debug,
            final_result=final_result,
            step_failed=step_failed,
            included_in_results=included
        ))

    def create_llm_debug(
        self,
        validation: "BatchValidationResult"
    ) -> Optional[LLMValidationDebug]:
        """Create LLM debug info from validation result. Returns None if disabled."""
        if not self.enabled:
            return None
        return LLMValidationDebug(
            is_valid_match=validation.is_valid_match,
            wine_name=validation.wine_name,
            confidence=validation.confidence,
            reasoning=validation.reasoning
        )


@dataclass
class RecognizedWine:
    """A recognized wine from the pipeline."""
    wine_name: str
    rating: Optional[float]  # None if not in database and no LLM estimate
    confidence: float
    source: str              # 'database' or 'llm'
    identified: bool         # True = show checkmark
    bottle_text: BottleText  # Original bottle context
    rating_source: str = "database"  # 'database' or 'llm_estimated'


class RecognitionPipeline:
    """
    Tiered recognition pipeline for wine labels.

    Flow:
    1. Batch fuzzy match all bottles against database
    2. High confidence (≥0.85) → return immediately, skip LLM
    3. Lower confidence → batch validate with single LLM call
    4. Process LLM results → re-match against DB if rejected
    """

    def __init__(
        self,
        wine_matcher: Optional[WineMatcher] = None,
        normalizer: Optional[NormalizerProtocol] = None,
        use_llm: bool = True,
        llm_provider: str = "claude",
        debug_mode: bool = False
    ):
        """
        Initialize pipeline.

        Args:
            wine_matcher: WineMatcher instance (default: creates new)
            normalizer: LLM normalizer (default: based on llm_provider)
            use_llm: Whether to use LLM fallback (disable for testing)
            llm_provider: LLM provider ("claude" or "gemini"). Default: "claude"
            debug_mode: If True, collect debug info for each step
        """
        self.wine_matcher = wine_matcher or WineMatcher()
        self.normalizer = normalizer or get_normalizer(use_mock=not use_llm, provider=llm_provider)
        self.use_llm = use_llm
        self.debug_mode = debug_mode
        # Debug data collection (encapsulated in DebugCollector)
        self._debug = DebugCollector(enabled=debug_mode)
        self.llm_call_count: int = 0

    @property
    def debug_steps(self) -> list[DebugPipelineStep]:
        """Access debug steps (for backwards compatibility)."""
        return self._debug.steps

    async def recognize(
        self,
        bottle_texts: list[BottleText]
    ) -> list[RecognizedWine]:
        """
        Recognize wines from bottle text clusters.

        Uses batched processing for efficiency:
        1. All bottles fuzzy matched in one pass
        2. High-confidence matches (≥0.85) skip LLM entirely
        3. Uncertain matches validated in single batched LLM call

        Args:
            bottle_texts: List of BottleText from OCR processor

        Returns:
            List of RecognizedWine with ratings where available
        """
        # Reset debug state for new recognition run
        self._debug.reset()
        self.llm_call_count = 0

        if not bottle_texts:
            return []

        # Phase 1: Batch fuzzy match (sync, fast)
        # Use match_with_scores when in debug mode for detailed scoring info
        matches: list[tuple[BottleText, Optional[WineMatch], Optional[WineMatchWithScores]]] = []
        for bottle_idx, bt in enumerate(bottle_texts):
            if not bt.normalized_name or len(bt.normalized_name) < 3:
                self._debug.add_step(
                    bt, bottle_idx, None, None, None,
                    step_failed="text_too_short", included=False
                )
                continue

            if self._debug.enabled:
                match_with_scores = self.wine_matcher.match_with_scores(bt.normalized_name)
                match = WineMatch(
                    canonical_name=match_with_scores.canonical_name,
                    rating=match_with_scores.rating,
                    confidence=match_with_scores.confidence,
                    source=match_with_scores.source
                ) if match_with_scores else None
                matches.append((bt, match, match_with_scores))
            else:
                match = self.wine_matcher.match(bt.normalized_name)
                matches.append((bt, match, None))

        # Phase 2: Partition by confidence
        high_confidence_results: list[RecognizedWine] = []
        needs_llm: list[tuple[BottleText, Optional[WineMatch], Optional[WineMatchWithScores], int]] = []

        for idx, (bt, match, match_with_scores) in enumerate(matches):
            bottle_idx = bottle_texts.index(bt)
            if match and match.confidence >= Config.HIGH_CONFIDENCE_THRESHOLD:
                # High confidence → skip LLM, return immediately
                result = self._match_to_result(bt, match)
                high_confidence_results.append(result)
                self._debug.add_step(
                    bt, bottle_idx, match_with_scores, None, result,
                    step_failed=None, included=True
                )
            elif self.use_llm:
                # Uncertain → queue for LLM validation
                needs_llm.append((bt, match, match_with_scores, bottle_idx))
            elif match and match.confidence >= Config.FUZZY_CONFIDENCE_THRESHOLD:
                # LLM disabled but acceptable confidence → use match
                result = self._match_to_result(bt, match)
                high_confidence_results.append(result)
                self._debug.add_step(
                    bt, bottle_idx, match_with_scores, None, result,
                    step_failed=None, included=True
                )
            else:
                # No match or low confidence, LLM disabled
                self._debug.add_step(
                    bt, bottle_idx, match_with_scores, None, None,
                    step_failed="low_confidence_no_llm", included=False
                )

        # Phase 3: Single batched LLM call for uncertain matches
        llm_results: list[RecognizedWine] = []
        if needs_llm:
            llm_results = await self._validate_batch_with_debug(needs_llm)

        return high_confidence_results + llm_results

    def _match_to_result(
        self,
        bottle_text: BottleText,
        match: WineMatch
    ) -> RecognizedWine:
        """Convert a fuzzy match to a RecognizedWine result."""
        return RecognizedWine(
            wine_name=match.canonical_name,
            rating=match.rating,
            confidence=min(bottle_text.bottle.confidence, match.confidence),
            source="database",
            identified=True,
            bottle_text=bottle_text,
            rating_source="database"
        )

    async def _validate_batch(
        self,
        items: list[tuple[BottleText, Optional[WineMatch]]]
    ) -> list[RecognizedWine]:
        """
        Validate multiple bottles in a single LLM call.

        Args:
            items: List of (BottleText, Optional[WineMatch]) tuples to validate

        Returns:
            List of RecognizedWine for successfully validated bottles
        """
        # Build batch request
        batch_items: list[BatchValidationItem] = []
        for bt, match in items:
            ocr_text = bt.combined_text or bt.normalized_name
            batch_items.append(BatchValidationItem(
                ocr_text=ocr_text,
                db_candidate=match.canonical_name if match else None,
                db_rating=match.rating if match else None
            ))

        # Single LLM call for all items
        validations = await self.normalizer.validate_batch(batch_items)
        self.llm_call_count += 1

        # Process results
        results: list[RecognizedWine] = []
        for (bt, match), validation in zip(items, validations):
            result = self._process_validation(bt, match, validation)
            if result:
                results.append(result)

        return results

    async def _validate_batch_with_debug(
        self,
        items: list[tuple[BottleText, Optional[WineMatch], Optional[WineMatchWithScores], int]]
    ) -> list[RecognizedWine]:
        """
        Validate multiple bottles with debug info collection.

        Args:
            items: List of (BottleText, WineMatch, WineMatchWithScores, bottle_idx) tuples

        Returns:
            List of RecognizedWine for successfully validated bottles
        """
        # Build batch request
        batch_items: list[BatchValidationItem] = []
        for bt, match, _, _ in items:
            ocr_text = bt.combined_text or bt.normalized_name
            batch_items.append(BatchValidationItem(
                ocr_text=ocr_text,
                db_candidate=match.canonical_name if match else None,
                db_rating=match.rating if match else None
            ))

        # Single LLM call for all items
        validations = await self.normalizer.validate_batch(batch_items)
        self.llm_call_count += 1

        # Process results with debug info
        results: list[RecognizedWine] = []
        for (bt, match, match_with_scores, bottle_idx), validation in zip(items, validations):
            result = self._process_validation(bt, match, validation)
            llm_debug = self._debug.create_llm_debug(validation)

            if result:
                self._debug.add_step(
                    bt, bottle_idx, match_with_scores, llm_debug, result,
                    step_failed=None, included=True
                )
                results.append(result)
            else:
                self._debug.add_step(
                    bt, bottle_idx, match_with_scores, llm_debug, None,
                    step_failed="llm_validation", included=False
                )

        return results

    def _process_validation(
        self,
        bottle_text: BottleText,
        match: Optional[WineMatch],
        validation: BatchValidationResult
    ) -> Optional[RecognizedWine]:
        """
        Process a single validation result from the batch.

        Flow:
        1. If LLM confirms match → use DB wine + rating
        2. If LLM rejects → try to match LLM's wine name against DB
        3. If found in DB → use DB wine + rating
        4. If not in DB → return LLM's name with LLM-estimated rating
        """
        # LLM confirmed the DB match
        if validation.is_valid_match and match:
            return RecognizedWine(
                wine_name=match.canonical_name,
                rating=match.rating,
                confidence=min(bottle_text.bottle.confidence, validation.confidence),
                source="database",
                identified=True,
                bottle_text=bottle_text,
                rating_source="database"
            )

        # LLM rejected the match - try to find the correct wine in DB
        if validation.wine_name:
            # Try matching the LLM-identified name against DB
            new_match = self.wine_matcher.match(validation.wine_name)

            # Only use DB match if it's high confidence AND different from rejected match
            rejected_name = match.canonical_name.lower() if match else ""
            new_match_name = new_match.canonical_name.lower() if new_match else ""

            if (new_match and
                new_match.confidence >= Config.FUZZY_CONFIDENCE_THRESHOLD and
                new_match_name != rejected_name):
                # Found a different, high-confidence wine in DB
                return RecognizedWine(
                    wine_name=new_match.canonical_name,
                    rating=new_match.rating,
                    confidence=min(validation.confidence, new_match.confidence),
                    source="database",
                    identified=True,
                    bottle_text=bottle_text,
                    rating_source="database"
                )

            # Wine not in DB (or only low-confidence matches) - use LLM-identified name
            # with LLM-estimated rating if available
            if validation.confidence >= 0.5:
                # Use LLM-estimated rating if provided, otherwise None
                rating = validation.estimated_rating
                rating_source = "llm_estimated" if rating is not None else "none"

                # If we have a rating, allow slightly higher confidence
                # If no rating, cap at 0.65 for de-emphasis
                if rating is not None:
                    capped_confidence = min(validation.confidence, 0.75)
                else:
                    capped_confidence = min(validation.confidence, 0.65)

                return RecognizedWine(
                    wine_name=validation.wine_name,
                    rating=rating,
                    confidence=capped_confidence,
                    source="llm",
                    identified=True,
                    bottle_text=bottle_text,
                    rating_source=rating_source
                )

        return None
