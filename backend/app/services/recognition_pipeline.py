"""
Tiered wine recognition pipeline.

Architecture:
1. Vision API → TEXT_DETECTION + OBJECT_LOCALIZATION
2. Text clustering → Group OCR fragments by bottle
3. Enhanced fuzzy matching → Try database match first (parallelized)
4. LLM fallback → For low-confidence/unknown wines (batched for performance)

Performance optimizations:
- High-confidence fuzzy matches (≥0.80) skip LLM entirely
- Lower-confidence matches are validated in a single batched LLM call
- Parallel fuzzy matching with ThreadPoolExecutor
- Expected latency: 1.5-2.5s for 8 bottles
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

from ..config import Config
from ..models.enums import RatingSource, WineSource
from ..models.debug import (
    DebugPipelineStep,
    FuzzyMatchDebug,
    FuzzyMatchScores,
    LLMValidationDebug,
    NearMissCandidate,
    NormalizationTrace,
    LLMRawDebug,
)
from .llm_normalizer import (
    NormalizerProtocol,
    BatchValidationItem,
    BatchValidationResult,
    get_normalizer,
)
from .llm_rating_cache import get_llm_rating_cache, LLMRatingCache
from .ocr_processor import BottleText
from .wine_matcher import WineMatcher, WineMatch, WineMatchWithScores, FuzzyMatchDebugResult, _is_generic_query, _is_llm_generic_response


class DebugCollector:
    """
    Collects debug information when enabled, no-ops when disabled.

    All debug assembly logic lives here — pipeline methods stay clean.
    """

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.steps: list[DebugPipelineStep] = []

    def reset(self) -> None:
        self.steps = []

    # --- Builder helpers (keep debug assembly out of pipeline code) ---

    def _build_fuzzy_debug(
        self,
        match_with_scores: Optional["WineMatchWithScores"],
        debug_result: Optional["FuzzyMatchDebugResult"] = None,
    ) -> Optional[FuzzyMatchDebug]:
        """Build FuzzyMatchDebug from match scores and optional debug result."""
        if debug_result is not None:
            # Rich debug path — includes near-misses even when match is None
            scores = None
            candidate = None
            rating = None
            if debug_result.match:
                m = debug_result.match
                candidate = m.canonical_name
                rating = m.rating
                scores = FuzzyMatchScores(
                    ratio=m.scores.ratio, partial_ratio=m.scores.partial_ratio,
                    token_sort_ratio=m.scores.token_sort_ratio,
                    phonetic_bonus=m.scores.phonetic_bonus,
                    weighted_score=m.scores.weighted_score,
                )
            near_misses = [
                NearMissCandidate(wine_name=nm.wine_name, score=nm.score, rejection_reason=nm.rejection_reason)
                for nm in debug_result.near_misses
            ]
            return FuzzyMatchDebug(
                candidate=candidate, scores=scores, rating=rating,
                near_misses=near_misses,
                fts_candidates_count=debug_result.fts_candidates_count,
                rejection_reason=debug_result.rejection_reason,
            )
        if match_with_scores:
            return FuzzyMatchDebug(
                candidate=match_with_scores.canonical_name,
                scores=FuzzyMatchScores(
                    ratio=match_with_scores.scores.ratio,
                    partial_ratio=match_with_scores.scores.partial_ratio,
                    token_sort_ratio=match_with_scores.scores.token_sort_ratio,
                    phonetic_bonus=match_with_scores.scores.phonetic_bonus,
                    weighted_score=match_with_scores.scores.weighted_score,
                ),
                rating=match_with_scores.rating,
            )
        return None

    def _build_normalization_trace(self, bottle_text: "BottleText") -> Optional[NormalizationTrace]:
        """Build NormalizationTrace from BottleText if trace data exists."""
        t = bottle_text.normalization_trace
        if not t:
            return None
        return NormalizationTrace(
            original_text=t["original_text"],
            after_pattern_removal=t["after_pattern_removal"],
            removed_patterns=t["removed_patterns"],
            removed_filler_words=t["removed_filler_words"],
            final_text=t["final_text"],
        )

    def _build_llm_raw(self, validation: Optional["BatchValidationResult"]) -> Optional[LLMRawDebug]:
        """Build LLMRawDebug from validation result debug fields."""
        if not validation:
            return None
        if validation._debug_heuristic:
            return LLMRawDebug(prompt_text="", raw_response="", was_heuristic_fallback=True)
        if validation._debug_prompt or validation._debug_response:
            return LLMRawDebug(
                prompt_text=validation._debug_prompt or "",
                raw_response=validation._debug_response or "",
                model_used=validation._debug_model,
            )
        return None

    # --- Public interface ---

    def add_step(
        self,
        bottle_text: "BottleText",
        bottle_idx: int,
        match_with_scores: Optional["WineMatchWithScores"],
        llm_debug: Optional[LLMValidationDebug],
        result: Optional["RecognizedWine"],
        step_failed: Optional[str],
        included: bool,
        debug_result: Optional["FuzzyMatchDebugResult"] = None,
        validation: Optional["BatchValidationResult"] = None,
    ) -> None:
        """Add a debug step. No-op if disabled."""
        if not self.enabled:
            return

        fuzzy_debug = self._build_fuzzy_debug(match_with_scores, debug_result)
        norm_trace = self._build_normalization_trace(bottle_text)
        llm_raw = self._build_llm_raw(validation)

        final_result = None
        if result:
            final_result = {
                "wine_name": result.wine_name,
                "confidence": result.confidence,
                "source": result.source,
            }

        self.steps.append(DebugPipelineStep(
            raw_text=bottle_text.combined_text or "",
            normalized_text=bottle_text.normalized_name or "",
            bottle_index=bottle_idx,
            fuzzy_match=fuzzy_debug,
            llm_validation=llm_debug,
            normalization_trace=norm_trace,
            llm_raw=llm_raw,
            final_result=final_result,
            step_failed=step_failed,
            included_in_results=included,
        ))

    def create_llm_debug(
        self,
        validation: "BatchValidationResult",
    ) -> Optional[LLMValidationDebug]:
        """Create LLM validation debug from result. Returns None if disabled."""
        if not self.enabled:
            return None
        return LLMValidationDebug(
            is_valid_match=validation.is_valid_match,
            wine_name=validation.wine_name,
            confidence=validation.confidence,
            reasoning=validation.reasoning,
        )


@dataclass
class RecognizedWine:
    """A recognized wine from the pipeline."""
    wine_name: str
    rating: Optional[float]  # None if not in database and no LLM estimate
    confidence: float
    source: WineSource       # WineSource.DATABASE or WineSource.LLM
    identified: bool         # True = show checkmark
    bottle_text: BottleText  # Original bottle context
    rating_source: RatingSource = RatingSource.DATABASE
    # Extended metadata from DB or LLM
    wine_type: Optional[str] = None
    brand: Optional[str] = None  # winery
    region: Optional[str] = None
    varietal: Optional[str] = None
    blurb: Optional[str] = None
    review_count: Optional[int] = None
    review_snippets: Optional[list[str]] = None
    wine_id: Optional[int] = None


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
        debug_mode: bool = False,
        use_llm_cache: Optional[bool] = None
    ):
        """
        Initialize pipeline.

        Args:
            wine_matcher: WineMatcher instance (default: creates new)
            normalizer: LLM normalizer (default: based on llm_provider)
            use_llm: Whether to use LLM fallback (disable for testing)
            llm_provider: LLM provider ("claude" or "gemini"). Default: "claude"
            debug_mode: If True, collect debug info for each step
            use_llm_cache: If True, cache LLM-identified wines. Default: uses Config.use_llm_cache()
        """
        self.wine_matcher = wine_matcher or WineMatcher()
        self.normalizer = normalizer or get_normalizer(use_mock=not use_llm)
        self.use_llm = use_llm
        self.debug_mode = debug_mode
        # Debug data collection (encapsulated in DebugCollector)
        self._debug = DebugCollector(enabled=debug_mode)
        self.llm_call_count: int = 0
        # Thread pool for parallel matching (reused across calls)
        self._executor = ThreadPoolExecutor(max_workers=4)
        # LLM rating cache for discovered wines
        cache_enabled = use_llm_cache if use_llm_cache is not None else Config.use_llm_cache()
        self._llm_cache: Optional[LLMRatingCache] = get_llm_rating_cache() if cache_enabled else None

    @property
    def debug_steps(self) -> list[DebugPipelineStep]:
        """Access debug steps (for backwards compatibility)."""
        return self._debug.steps

    def _match_bottle(
        self,
        bt: BottleText,
        bottle_idx: int
    ) -> tuple[BottleText, Optional[WineMatch], Optional[WineMatchWithScores], int, Optional[str], Optional[FuzzyMatchDebugResult]]:
        """
        Match a single bottle (for parallel execution).

        Returns:
            Tuple of (bottle_text, match, match_with_scores, bottle_idx, error_reason, debug_result)
        """
        if not bt.normalized_name or len(bt.normalized_name) < 3:
            raw_text = bt.combined_text or ""
            if len(raw_text.strip()) >= 5:
                logger.info(
                    f"Bottle {bottle_idx}: normalized text too short "
                    f"({bt.normalized_name!r}) but raw text available "
                    f"({raw_text[:60]!r}), forwarding to LLM"
                )
                return (bt, None, None, bottle_idx, None, None)
            return (bt, None, None, bottle_idx, "text_too_short", None)

        if self._debug.enabled:
            debug_result = self.wine_matcher.match_with_debug(bt.normalized_name)
            match_with_scores = debug_result.match
            match = WineMatch(
                canonical_name=match_with_scores.canonical_name,
                rating=match_with_scores.rating,
                confidence=match_with_scores.confidence,
                source=match_with_scores.source,
                wine_type=match_with_scores.wine_type,
                brand=match_with_scores.brand,
                region=match_with_scores.region,
                varietal=match_with_scores.varietal,
                description=match_with_scores.description,
            ) if match_with_scores else None
            return (bt, match, match_with_scores, bottle_idx, None, debug_result)
        else:
            match = self.wine_matcher.match(bt.normalized_name)
            return (bt, match, None, bottle_idx, None, None)

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

        # Phase 1: Parallel fuzzy match (optimized with ThreadPoolExecutor)
        matches: list[tuple[BottleText, Optional[WineMatch], Optional[WineMatchWithScores], Optional[FuzzyMatchDebugResult]]] = []

        futures = [
            self._executor.submit(self._match_bottle, bt, idx)
            for idx, bt in enumerate(bottle_texts)
        ]

        for idx, future in enumerate(futures):
            try:
                bt, match, match_with_scores, bottle_idx, error_reason, debug_result = future.result()
                if error_reason:
                    self._debug.add_step(
                        bt, bottle_idx, None, None, None,
                        step_failed=error_reason, included=False,
                        debug_result=debug_result,
                    )
                    continue
                matches.append((bt, match, match_with_scores, debug_result))
            except Exception as e:
                logger.error(f"Error matching bottle {idx}: {e}", exc_info=True)
                bt = bottle_texts[idx]
                self._debug.add_step(
                    bt, idx, None, None, None,
                    step_failed=f"matching_exception: {type(e).__name__}", included=False,
                )

        # Phase 2: Partition by confidence
        high_confidence_results: list[RecognizedWine] = []
        needs_llm: list[tuple[BottleText, Optional[WineMatch], Optional[WineMatchWithScores], int, Optional[FuzzyMatchDebugResult]]] = []

        for idx, (bt, match, match_with_scores, debug_result) in enumerate(matches):
            bottle_idx = bottle_texts.index(bt)
            if match and match.confidence >= Config.HIGH_CONFIDENCE_THRESHOLD:
                result = self._match_to_result(bt, match)
                high_confidence_results.append(result)
                self._debug.add_step(
                    bt, bottle_idx, match_with_scores, None, result,
                    step_failed=None, included=True,
                    debug_result=debug_result,
                )
            elif self.use_llm:
                needs_llm.append((bt, match, match_with_scores, bottle_idx, debug_result))
            elif match and match.confidence >= Config.FUZZY_CONFIDENCE_THRESHOLD:
                result = self._match_to_result(bt, match)
                high_confidence_results.append(result)
                self._debug.add_step(
                    bt, bottle_idx, match_with_scores, None, result,
                    step_failed=None, included=True,
                    debug_result=debug_result,
                )
            else:
                self._debug.add_step(
                    bt, bottle_idx, match_with_scores, None, None,
                    step_failed="low_confidence_no_llm", included=False,
                    debug_result=debug_result,
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
            source=WineSource.DATABASE,
            identified=True,
            bottle_text=bottle_text,
            rating_source=RatingSource.DATABASE,
            wine_type=match.wine_type,
            brand=match.brand,
            region=match.region,
            varietal=match.varietal,
            review_snippets=[match.description] if match.description else None,
            wine_id=match.wine_id,
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
        items: list[tuple[BottleText, Optional[WineMatch], Optional[WineMatchWithScores], int, Optional[FuzzyMatchDebugResult]]]
    ) -> list[RecognizedWine]:
        """
        Validate multiple bottles with debug info collection.

        Args:
            items: List of (BottleText, WineMatch, WineMatchWithScores, bottle_idx, debug_result) tuples

        Returns:
            List of RecognizedWine for successfully validated bottles
        """
        results: list[RecognizedWine] = []
        items_needing_llm: list[tuple[BottleText, Optional[WineMatch], Optional[WineMatchWithScores], int, Optional[FuzzyMatchDebugResult]]] = []
        cache_hit_indices: set[int] = set()

        # Phase 1: Check cache for ALL items
        if self._llm_cache:
            for idx, (bt, match, match_with_scores, bottle_idx, debug_result) in enumerate(items):
                ocr_text = bt.combined_text or bt.normalized_name
                cached = self._llm_cache.get(ocr_text)
                if cached and (len(cached.wine_name) > 80 or len(cached.wine_name.split()) > 10):
                    cached = None
                if not cached and bt.normalized_name and bt.normalized_name != ocr_text:
                    cached = self._llm_cache.get(bt.normalized_name)
                if cached and (len(cached.wine_name) > 80 or len(cached.wine_name.split()) > 10):
                    cached = None
                if cached:
                    result = RecognizedWine(
                        wine_name=cached.wine_name,
                        rating=cached.estimated_rating,
                        confidence=min(bt.bottle.confidence, cached.confidence),
                        source=WineSource.LLM,
                        identified=True,
                        bottle_text=bt,
                        rating_source=RatingSource.LLM_ESTIMATED,
                        wine_type=cached.wine_type,
                        brand=cached.brand,
                        region=cached.region,
                        varietal=cached.varietal,
                    )
                    results.append(result)
                    cache_hit_indices.add(idx)

                    cache_debug = LLMValidationDebug(
                        is_valid_match=True,
                        wine_name=cached.wine_name,
                        confidence=cached.confidence,
                        reasoning=f"Cache hit (provider: {cached.llm_provider}, hits: {cached.hit_count})"
                    )
                    self._debug.add_step(
                        bt, bottle_idx, match_with_scores, cache_debug, result,
                        step_failed=None, included=True,
                        debug_result=debug_result,
                    )

        # Collect items that still need LLM validation
        for idx, item in enumerate(items):
            if idx not in cache_hit_indices:
                items_needing_llm.append(item)

        # Phase 2: Call LLM for remaining items
        if items_needing_llm:
            batch_items: list[BatchValidationItem] = []
            for bt, match, _, _, _ in items_needing_llm:
                ocr_text = bt.combined_text or bt.normalized_name
                batch_items.append(BatchValidationItem(
                    ocr_text=ocr_text,
                    db_candidate=match.canonical_name if match else None,
                    db_rating=match.rating if match else None
                ))

            validations = await self.normalizer.validate_batch(batch_items)
            self.llm_call_count += 1

            for (bt, match, match_with_scores, bottle_idx, debug_result), validation in zip(items_needing_llm, validations):
                result = self._process_validation(bt, match, validation)
                llm_debug = self._debug.create_llm_debug(validation)

                if result:
                    self._debug.add_step(
                        bt, bottle_idx, match_with_scores, llm_debug, result,
                        step_failed=None, included=True,
                        debug_result=debug_result,
                        validation=validation,
                    )
                    results.append(result)
                else:
                    self._debug.add_step(
                        bt, bottle_idx, match_with_scores, llm_debug, None,
                        step_failed="llm_validation", included=False,
                        debug_result=debug_result,
                        validation=validation,
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
        1. If LLM confirms match → use DB wine + rating + LLM metadata
        2. If LLM rejects → try to match LLM's wine name against DB
        3. If found in DB → use DB wine + rating
        4. If not in DB → return LLM's name with LLM-estimated rating + metadata
        """
        # LLM confirmed the DB match
        if validation.is_valid_match and match:
            return RecognizedWine(
                wine_name=match.canonical_name,
                rating=match.rating,
                confidence=min(bottle_text.bottle.confidence, validation.confidence),
                source=WineSource.DATABASE,
                identified=True,
                bottle_text=bottle_text,
                rating_source=RatingSource.DATABASE,
                # Use DB metadata, fall back to LLM metadata
                wine_type=match.wine_type or validation.wine_type,
                brand=match.brand or validation.brand,
                region=match.region,
                varietal=match.varietal,
                blurb=validation.blurb,  # Always from LLM
                review_count=validation.review_count,
                # Prefer DB description over LLM snippets for confirmed DB matches
                review_snippets=[match.description] if match.description else validation.review_snippets,
                wine_id=match.wine_id,
            )

        # LLM rejected the match - try to find the correct wine in DB
        if validation.wine_name:
            # Try matching the LLM-identified name against DB
            new_match = self.wine_matcher.match(validation.wine_name)

            # Only use DB match if confidence is VERY high (0.95+) to avoid false positives
            # When fuzzy matching gives 0.85-0.94, it's often a wrong match
            # (e.g., "Crimson Ranch" -> "Brown Ranch")
            rejected_name = match.canonical_name.lower() if match else ""
            new_match_name = new_match.canonical_name.lower() if new_match else ""

            if (new_match and
                new_match.confidence >= 0.95 and  # Very high threshold for re-matching
                new_match_name != rejected_name):
                # Found a different, very-high-confidence wine in DB
                return RecognizedWine(
                    wine_name=new_match.canonical_name,
                    rating=new_match.rating,
                    confidence=min(validation.confidence, new_match.confidence),
                    source=WineSource.DATABASE,
                    identified=True,
                    bottle_text=bottle_text,
                    rating_source=RatingSource.DATABASE,
                    wine_type=new_match.wine_type or validation.wine_type,
                    brand=new_match.brand or validation.brand,
                    region=new_match.region,
                    varietal=new_match.varietal,
                    blurb=validation.blurb,
                    review_count=validation.review_count,
                    # Prefer DB description over LLM snippets for DB matches
                    review_snippets=[new_match.description] if new_match.description else validation.review_snippets,
                    wine_id=new_match.wine_id,
                )

            # Wine not in DB (or only low-confidence matches) - use LLM-identified name
            # with LLM-estimated rating if available
            if validation.confidence >= 0.5:
                # Skip if LLM returned a generic wine name (would cause false positives)
                if _is_llm_generic_response(validation.wine_name):
                    return None

                # Use LLM-estimated rating if provided, otherwise None
                rating = validation.estimated_rating
                rating_source = RatingSource.LLM_ESTIMATED if rating is not None else RatingSource.NONE

                # If we have a rating, allow slightly higher confidence
                # If no rating, cap at 0.65 for de-emphasis
                if rating is not None:
                    capped_confidence = min(validation.confidence, 0.75)
                else:
                    capped_confidence = min(validation.confidence, 0.65)

                result = RecognizedWine(
                    wine_name=validation.wine_name,
                    rating=rating,
                    confidence=capped_confidence,
                    source=WineSource.LLM,
                    identified=True,
                    bottle_text=bottle_text,
                    rating_source=rating_source,
                    wine_type=validation.wine_type,
                    brand=validation.brand,
                    region=validation.region,
                    varietal=validation.varietal,
                    blurb=validation.blurb,
                    review_count=validation.review_count,
                    review_snippets=validation.review_snippets,
                )

                # Cache the LLM-identified wine for future lookups
                # Skip caching garbage names (too long or too many words)
                if self._llm_cache and rating is not None and len(validation.wine_name) <= 80 and len(validation.wine_name.split()) <= 10:
                    llm_provider = self.normalizer.models[0] if hasattr(self.normalizer, 'models') else 'unknown'
                    cache_kwargs = dict(
                        estimated_rating=rating,
                        confidence=capped_confidence,
                        llm_provider=llm_provider,
                        wine_type=validation.wine_type,
                        region=validation.region,
                        varietal=validation.varietal,
                        brand=validation.brand,
                    )
                    # Cache under the canonical wine name
                    self._llm_cache.set(wine_name=validation.wine_name, **cache_kwargs)
                    # Also cache under the raw OCR text so future scans
                    # can find it without re-calling the LLM
                    ocr_text = bottle_text.combined_text or bottle_text.normalized_name
                    if ocr_text and len(ocr_text) <= 80 and ocr_text.lower() != validation.wine_name.lower():
                        self._llm_cache.set(wine_name=ocr_text, **cache_kwargs)
                    if (bottle_text.normalized_name
                            and len(bottle_text.normalized_name) <= 80
                            and bottle_text.normalized_name.lower() != validation.wine_name.lower()
                            and bottle_text.normalized_name != ocr_text):
                        self._llm_cache.set(wine_name=bottle_text.normalized_name, **cache_kwargs)

                return result

        return None
