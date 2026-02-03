"""
LLM-based OCR text normalization for wine labels.

Uses LiteLLM for unified LLM access with automatic fallbacks between providers.
Swappable via the NormalizerProtocol.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional, Protocol

# Lazy import for litellm to avoid slow network requests during module load
# litellm fetches model info from GitHub during import, causing startup delays
_litellm = None
_litellm_checked = False


def _get_litellm():
    """Lazy-load litellm to avoid startup delays from network requests."""
    global _litellm, _litellm_checked
    if not _litellm_checked:
        _litellm_checked = True
        try:
            import litellm
            litellm.set_verbose = False  # Suppress logging noise
            _litellm = litellm
        except ModuleNotFoundError:
            _litellm = None
    return _litellm


def _litellm_available() -> bool:
    """Check if litellm is available without triggering import."""
    if _litellm_checked:
        return _litellm is not None
    # Check if module exists without importing
    import importlib.util
    return importlib.util.find_spec("litellm") is not None


# For backwards compatibility
LITELLM_AVAILABLE = _litellm_available()

logger = logging.getLogger(__name__)


def _extract_clean_wine_name(ocr_text: str) -> Optional[str]:
    """
    Extract a clean wine name from raw OCR text.

    When heuristic validation rejects a match but we want to return
    something, extract just the likely wine name (first few words)
    rather than the full OCR garbage.

    Returns None if no valid wine name can be extracted.
    """
    if not ocr_text:
        return None

    # Split into words
    words = ocr_text.strip().split()
    if not words:
        return None

    # Take first 3-5 words (typical wine name length)
    # Stop at common OCR noise markers
    noise_markers = {
        'the', 'and', 'from', 'made', 'crafted', 'journal', 'worldwide',
        'grown', 'bown', 'area', 'where', '-', '—', '–'
    }

    clean_words = []
    for word in words[:6]:  # Max 6 words
        word_lower = word.lower().strip('.,;:!?')
        # Stop if we hit noise
        if word_lower in noise_markers and len(clean_words) >= 2:
            break
        # Skip very short words after first word
        if len(word_lower) <= 2 and clean_words:
            continue
        clean_words.append(word)

    if not clean_words:
        return None

    # Join and title case
    result = ' '.join(clean_words).strip()

    # Reject if too long (likely still garbage)
    if len(result) > 50:
        return None

    # Reject if it doesn't look like a wine name (no alpha characters)
    if not any(c.isalpha() for c in result):
        return None

    return result.title()


@dataclass
class NormalizationResult:
    """Result from LLM normalization."""
    wine_name: Optional[str]  # Canonical name or None if not parseable
    confidence: float         # 0.0-1.0
    is_wine: bool             # True if this appears to be a wine label
    reasoning: str            # Brief explanation


@dataclass
class ValidationResult:
    """Result from LLM validation of a DB match."""
    is_valid_match: bool      # True if DB candidate correctly matches OCR text
    wine_name: Optional[str]  # Correct wine name (from DB or identified by LLM)
    confidence: float         # 0.0-1.0
    reasoning: str            # Brief explanation


@dataclass
class BatchValidationItem:
    """Input item for batch validation."""
    ocr_text: str
    db_candidate: Optional[str]
    db_rating: Optional[float]


@dataclass
class BatchValidationResult:
    """Result for a single item in batch validation."""
    index: int                # Index in the input batch
    is_valid_match: bool
    wine_name: Optional[str]
    confidence: float
    reasoning: str
    estimated_rating: Optional[float] = None  # LLM-estimated rating for wines not in DB
    # Extended metadata from LLM
    wine_type: Optional[str] = None  # Red, White, Rosé, Sparkling, etc.
    brand: Optional[str] = None  # Winery/producer name
    region: Optional[str] = None  # Wine region (Napa Valley, Burgundy, etc.)
    varietal: Optional[str] = None  # Grape variety (Cabernet Sauvignon, Pinot Noir, etc.)
    blurb: Optional[str] = None  # 1-2 sentence description
    review_count: Optional[int] = None  # Estimated review count
    review_snippets: Optional[list[str]] = None  # Sample review quotes


class NormalizerProtocol(Protocol):
    """Protocol for wine name normalizers (allows swapping LLM providers)."""
    async def normalize(
        self,
        ocr_text: str,
        context: Optional[dict] = None
    ) -> NormalizationResult: ...

    async def validate(
        self,
        ocr_text: str,
        db_candidate: Optional[str],
        db_rating: Optional[float]
    ) -> ValidationResult: ...

    async def validate_batch(
        self,
        items: list[BatchValidationItem]
    ) -> list[BatchValidationResult]: ...


class LLMNormalizerBase:
    """
    Base class with shared parsing/validation logic for LLM normalizers.

    Contains prompts and response parsing methods used by LiteLLMNormalizer.
    """

    VALIDATION_PROMPT = """You are a wine label validator.

Given OCR text from a wine bottle and a database match candidate, determine:
1. Is the database candidate a correct match for the OCR text?
2. If not, what is the actual wine name from the OCR?

## MATCHING RULES

VALID MATCH if:
- The database wine name is the same wine as the OCR text
- Acceptable differences: vintage year, "Reserve", regional suffixes
- Example: OCR "CRIMSON RANCH" matches DB "Crimson Ranch 2014 Cabernet Sauvignon" ✓

INVALID MATCH if:
- The wines are clearly different
- The DB candidate is a substring trick (OCR "VENNSTONE" ≠ DB "One")
- The DB candidate has different producer name
- Example: OCR "PRECIPICE" does NOT match DB "Ice" ✗

## OUTPUT

Return JSON only:
{"is_valid_match": true/false, "wine_name": "correct wine name", "confidence": 0.0-1.0, "reasoning": "brief explanation"}

If invalid match, wine_name should be the actual wine from the OCR text (cleaned up)."""

    BATCH_VALIDATION_PROMPT = """You are a wine label validator processing multiple bottles at once.

For each item, you are given OCR text from a wine bottle and optionally a database match candidate.
Determine if the match is correct, or identify the actual wine name.

## CRITICAL: WHAT IS NOT A WINE NAME

NEVER return these as wine names - return wine_name=null instead:
- Marketing text: "All Our Wines Are...", "Sustainably Produced", "Family Owned"
- Generic wine terms WITHOUT a producer: "Barolo Denominazione", "Grand Vin de Bordeaux", "Champagne Brut"
- Label boilerplate: "Mis en Bouteille", "Product of France", "Contains Sulfites"
- Prices, dates, barcodes, numbers without context
- Partial OCR fragments that don't form a complete wine name

A VALID wine name MUST include at least one of:
- A specific producer/winery name (e.g., "Ruffino", "Louis Latour", "Caymus")
- A specific vineyard or cuvée name (e.g., "Martha's Vineyard", "Cuvée Prestige")

Examples:
- "Ruffino Chianti" ✓ (has producer Ruffino)
- "Barolo DOCG" ✗ (no producer, just region/classification)
- "All Our Wines Are Sustainably" ✗ (marketing text)
- "Grand Vin de Bordeaux" ✗ (generic term, no producer)

## MATCHING RULES

VALID MATCH if:
- The database wine name is the same wine as the OCR text
- Acceptable differences: vintage year, "Reserve", regional suffixes

INVALID MATCH if:
- The wines are clearly different
- The DB candidate is a substring trick (OCR "VENNSTONE" ≠ DB "One")
- The DB candidate has different producer name

NO CANDIDATE:
- If db_candidate is null, identify the wine name from the OCR text
- If no valid wine name can be identified, return wine_name=null and confidence=0.0

## RATING AND METADATA

For ALL wines where wine_name is not null, provide:
- wine_type: "Red", "White", "Rosé", "Sparkling", "Dessert", or "Fortified"
- brand: The producer/winery name (e.g., "Caymus", "Château Margaux")
- region: The wine region (e.g., "Napa Valley", "Burgundy", "Marlborough")
- varietal: The grape variety (e.g., "Cabernet Sauvignon", "Pinot Noir", "Chardonnay")
- blurb: 2-3 sentences about the wine or winery - include tasting notes, history, or what makes it special
- review_count: Estimated number of reviews (based on wine popularity, 50-50000 range)
- review_snippets: Array of 2-3 short review quotes (be creative but realistic)

For wines NOT in our database (when db_candidate is null or match is invalid):
- Also provide estimated_rating (1.0-5.0) based on your wine knowledge
- Default to 3.7-4.0 if uncertain (typical mid-tier wine)

## OUTPUT

Return a JSON array with one result per input item (same order):
[
  {"index": 0, "is_valid_match": true, "wine_name": "Caymus Cabernet Sauvignon", "confidence": 0.95, "reasoning": "...", "wine_type": "Red", "brand": "Caymus Vineyards", "region": "Napa Valley", "varietal": "Cabernet Sauvignon", "blurb": "Caymus is one of Napa Valley's most celebrated wineries, founded in 1972 by the Wagner family. Their Cabernet Sauvignon is known for its rich, velvety texture with layers of dark fruit, cocoa, and vanilla from French oak aging.", "review_count": 12500, "review_snippets": ["Silky smooth with notes of blackberry", "A Napa classic that never disappoints"]},
  {"index": 1, "is_valid_match": false, "wine_name": "Wente Morning Fog Chardonnay", "confidence": 0.85, "reasoning": "Valid wine but not in database", "estimated_rating": 3.9, "wine_type": "White", "brand": "Wente Vineyards", "region": "Livermore Valley", "varietal": "Chardonnay", "blurb": "Wente Vineyards is America's oldest continuously operated family winery, established in 1883 in Livermore Valley. Their Morning Fog Chardonnay offers bright citrus and green apple notes with a touch of vanilla from subtle oak influence.", "review_count": 3200, "review_snippets": ["Crisp and refreshing", "Great value Chardonnay"]},
  {"index": 2, "is_valid_match": false, "wine_name": null, "confidence": 0.0, "reasoning": "No valid wine name found"},
  ...
]"""

    SYSTEM_PROMPT = """You are a wine label text analyzer.

Given OCR text from a wine shelf photo, determine if it contains a wine name and extract it.

## ANALYSIS APPROACH

First, identify what patterns are present in the text:

WINE INDICATORS:
- Producer/winery names (Caymus, Opus One, Château Margaux)
- Grape varietals (Cabernet Sauvignon, Pinot Noir, Chardonnay)
- Wine regions (Napa Valley, Sonoma, Burgundy, Rioja)
- Wine terminology (Reserve, Estate, Vineyard, Cuvée)

NON-WINE INDICATORS:
- Price tags ($X.XX, SALE, SPECIAL, % OFF)
- Warning/legal text (Contains sulfites, Government Warning, Drink Responsibly)
- Barcodes, SKU numbers, or inventory codes only
- Store signage or promotional copy
- Disconnected OCR fragments with no wine context

## DECISION LOGIC

Based on your pattern analysis:
- If wine indicators present → Extract the canonical wine name
- If ONLY non-wine indicators → Return is_wine=false
- If mixed (wine name + price/warning) → Extract the wine name, ignore the rest

## EXTRACTION RULES

When extracting the wine name:
- Combine producer + varietal (e.g., "Caymus" + "Cabernet Sauvignon" → "Caymus Cabernet Sauvignon")
- REMOVE: vintage years, bottle sizes (750ml), ABV%, awards, marketing phrases
- INFER complete name from partial text when possible (e.g., "aymus Cab" → "Caymus Cabernet Sauvignon")

## OUTPUT

Return JSON only:
{"is_wine": true/false, "wine_name": "..." or null, "confidence": 0.0-1.0, "reasoning": "..."}

Confidence:
- 0.9+: Clear, complete wine name visible
- 0.7-0.9: Partial but identifiable
- 0.5-0.7: Inferred from fragments
- <0.5: Very uncertain"""

    def _parse_response(self, response_text: str) -> NormalizationResult:
        """Parse LLM JSON response for normalization."""
        try:
            # Handle potential markdown code blocks
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            data = json.loads(text)

            return NormalizationResult(
                wine_name=data.get("wine_name"),
                confidence=float(data.get("confidence", 0.5)),
                is_wine=bool(data.get("is_wine", False)),
                reasoning=data.get("reasoning", "")
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            return NormalizationResult(
                wine_name=None,
                confidence=0.0,
                is_wine=False,
                reasoning=f"Parse error: {str(e)}"
            )

    def _parse_validation_response(
        self,
        response_text: str,
        db_candidate: str
    ) -> ValidationResult:
        """Parse LLM validation JSON response."""
        try:
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            data = json.loads(text)

            return ValidationResult(
                is_valid_match=bool(data.get("is_valid_match", False)),
                wine_name=data.get("wine_name") or db_candidate,
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", "")
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse validation response: {e}")
            return ValidationResult(
                is_valid_match=True,
                wine_name=db_candidate,
                confidence=0.5,
                reasoning=f"Parse error, trusting fuzzy match: {str(e)}"
            )

    def _heuristic_validate(
        self,
        ocr_text: str,
        db_candidate: Optional[str]
    ) -> ValidationResult:
        """Validate without LLM using simple heuristics."""
        if not db_candidate:
            clean_name = _extract_clean_wine_name(ocr_text)
            return ValidationResult(
                is_valid_match=False,
                wine_name=clean_name,
                confidence=0.5 if clean_name else 0.0,
                reasoning="No DB candidate"
            )

        ocr_lower = ocr_text.lower().strip()
        db_lower = db_candidate.lower().strip()

        # Get first words (usually producer name)
        ocr_first = ocr_lower.split()[0] if ocr_lower else ""
        db_first = db_lower.split()[0] if db_lower else ""

        # Check 1: DB candidate much shorter = likely substring abuse
        if len(db_lower) < len(ocr_lower) * 0.4:
            clean_name = _extract_clean_wine_name(ocr_text)
            return ValidationResult(
                is_valid_match=False,
                wine_name=clean_name,
                confidence=0.6 if clean_name else 0.0,
                reasoning="DB candidate too short"
            )

        # Check 2: First word should match (producer name)
        if ocr_first and db_first and len(ocr_first) >= 3:
            # Check if first words are similar enough
            # Use longer prefix for longer words to avoid false positives
            min_match_len = min(4, len(ocr_first), len(db_first))
            if ocr_first[:min_match_len] != db_first[:min_match_len]:
                # First words don't match - check if either is contained in the other
                if ocr_lower not in db_lower and db_lower.split()[0] not in ocr_lower:
                    clean_name = _extract_clean_wine_name(ocr_text)
                    return ValidationResult(
                        is_valid_match=False,
                        wine_name=clean_name,
                        confidence=0.6 if clean_name else 0.0,
                        reasoning="Producer names don't match"
                    )

        # Check 3: If first words match prefix but are very different overall, reject
        # e.g., "precipice" vs "premices" both start with "pre" but are different
        if ocr_first and db_first and len(ocr_first) >= 5 and len(db_first) >= 5:
            # Check middle characters
            if ocr_first[2:5] != db_first[2:5]:
                clean_name = _extract_clean_wine_name(ocr_text)
                return ValidationResult(
                    is_valid_match=False,
                    wine_name=clean_name,
                    confidence=0.6 if clean_name else 0.0,
                    reasoning="First words differ in middle characters"
                )

        # Passed heuristics - trust the match
        return ValidationResult(
            is_valid_match=True,
            wine_name=db_candidate,
            confidence=0.7,
            reasoning="Heuristic validation passed"
        )

    def _format_batch_items(self, items: list[BatchValidationItem]) -> str:
        """Format batch items for LLM prompt."""
        lines = []
        for i, item in enumerate(items):
            rating_str = f"{item.db_rating:.1f}" if item.db_rating else "N/A"
            db_str = f'"{item.db_candidate}" (rating: {rating_str})' if item.db_candidate else "null"
            lines.append(f'{i}. OCR: "{item.ocr_text}" → DB: {db_str}')
        return "\n".join(lines)

    def _parse_batch_response(
        self,
        response_text: str,
        items: list[BatchValidationItem]
    ) -> list[BatchValidationResult]:
        """Parse LLM batch validation JSON response."""
        try:
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            data = json.loads(text)

            if not isinstance(data, list):
                raise ValueError("Expected JSON array")

            results = []
            for i, item in enumerate(items):
                result_data = next((d for d in data if d.get("index") == i), None)

                if result_data:
                    # Extract estimated_rating if present
                    estimated_rating = result_data.get("estimated_rating")
                    if estimated_rating is not None:
                        estimated_rating = float(estimated_rating)
                        # Clamp to valid range
                        estimated_rating = max(1.0, min(5.0, estimated_rating))

                    # Extract review_count if present
                    review_count = result_data.get("review_count")
                    if review_count is not None:
                        review_count = int(review_count)

                    # Extract review_snippets
                    review_snippets = result_data.get("review_snippets")
                    if review_snippets and not isinstance(review_snippets, list):
                        review_snippets = None

                    results.append(BatchValidationResult(
                        index=i,
                        is_valid_match=bool(result_data.get("is_valid_match", False)),
                        wine_name=result_data.get("wine_name") or item.db_candidate,
                        confidence=float(result_data.get("confidence", 0.5)),
                        reasoning=result_data.get("reasoning", ""),
                        estimated_rating=estimated_rating,
                        wine_type=result_data.get("wine_type"),
                        brand=result_data.get("brand"),
                        region=result_data.get("region"),
                        varietal=result_data.get("varietal"),
                        blurb=result_data.get("blurb"),
                        review_count=review_count,
                        review_snippets=review_snippets,
                    ))
                else:
                    heuristic = self._heuristic_validate(item.ocr_text, item.db_candidate)
                    results.append(BatchValidationResult(
                        index=i,
                        is_valid_match=heuristic.is_valid_match,
                        wine_name=heuristic.wine_name,
                        confidence=heuristic.confidence,
                        reasoning="Fallback: missing from LLM response",
                        estimated_rating=None
                    ))

            return results

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse batch response: {e}")
            return self._heuristic_validate_batch(items)

    def _heuristic_validate_batch(
        self,
        items: list[BatchValidationItem]
    ) -> list[BatchValidationResult]:
        """Validate batch without LLM using heuristics."""
        results = []
        for i, item in enumerate(items):
            heuristic = self._heuristic_validate(item.ocr_text, item.db_candidate)
            results.append(BatchValidationResult(
                index=i,
                is_valid_match=heuristic.is_valid_match,
                wine_name=heuristic.wine_name,
                confidence=heuristic.confidence,
                reasoning=heuristic.reasoning,
                estimated_rating=None  # Heuristics can't estimate ratings
            ))
        return results


class LiteLLMNormalizer(LLMNormalizerBase):
    """
    Wine name normalizer using LiteLLM (unified interface with automatic fallbacks).

    Benefits:
    - Automatic fallback between providers on errors/rate limits
    - Unified API for 100+ LLM providers
    - Built-in retry logic with exponential backoff
    - Cost tracking built-in

    Inherits shared parsing/validation logic from LLMNormalizerBase.
    """

    # Default model fallback chain (fastest/cheapest first)
    DEFAULT_MODELS = [
        "gemini/gemini-2.0-flash",       # Primary: fastest, cheapest
        "claude-3-haiku-20240307",       # Fallback 1: reliable
        "gpt-4o-mini",                   # Fallback 2: widely available
    ]

    def __init__(
        self,
        models: Optional[list[str]] = None,
        num_retries: int = 2,
        timeout: float = 30.0,
    ):
        """
        Initialize normalizer with fallback chain.

        Args:
            models: List of model names in priority order (first = primary).
                    If not provided, builds from environment config.
            num_retries: Retries per model before trying fallback.
            timeout: Request timeout in seconds.
        """
        self.models = models or self._get_configured_models()
        self.num_retries = num_retries
        self.timeout = timeout
        # Note: litellm.set_verbose is set in _get_litellm() when first loaded

    def _get_configured_models(self) -> list[str]:
        """Build model list from environment config."""
        from ..config import Config

        models = []

        # Primary model from LLM_PROVIDER env var
        provider = Config.llm_provider()
        if provider == "gemini" and Config.gemini_api_key():
            models.append(f"gemini/{Config.gemini_model()}")
        elif provider == "claude" and Config.anthropic_api_key():
            models.append("claude-3-haiku-20240307")

        # Add fallbacks for any other configured providers
        if Config.gemini_api_key() and not any("gemini" in m for m in models):
            models.append(f"gemini/{Config.gemini_model()}")
        if Config.anthropic_api_key() and not any("claude" in m for m in models):
            models.append("claude-3-haiku-20240307")
        if Config.openai_api_key() and not any("gpt" in m for m in models):
            models.append("gpt-4o-mini")

        return models if models else []

    async def normalize(
        self,
        ocr_text: str,
        context: Optional[dict] = None
    ) -> NormalizationResult:
        """
        Normalize OCR text to canonical wine name using LiteLLM.

        Args:
            ocr_text: Raw OCR text from the bottle
            context: Optional context (bottle position, confidence, etc.)

        Returns:
            NormalizationResult with wine_name, confidence, is_wine
        """
        if not ocr_text or len(ocr_text.strip()) < 3:
            return NormalizationResult(
                wine_name=None,
                confidence=0.0,
                is_wine=False,
                reasoning="Text too short"
            )

        if not LITELLM_AVAILABLE:
            logger.warning("litellm not installed, cannot normalize")
            return NormalizationResult(
                wine_name=None,
                confidence=0.0,
                is_wine=False,
                reasoning="LiteLLM not available"
            )

        if not self.models:
            logger.warning("No LLM models configured")
            return NormalizationResult(
                wine_name=None,
                confidence=0.0,
                is_wine=False,
                reasoning="No LLM providers configured"
            )

        # Build prompt
        user_prompt = f'OCR Text: "{ocr_text}"'
        if context:
            user_prompt += f"\nContext: {json.dumps(context)}"
        user_prompt += """

Return JSON: {"wine_name": "...", "confidence": 0.0-1.0, "is_wine": true/false, "reasoning": "..."}"""

        full_prompt = f"{self.SYSTEM_PROMPT}\n\n{user_prompt}"

        try:
            litellm = _get_litellm()
            if not litellm:
                raise RuntimeError("LiteLLM not available")
            response = await litellm.acompletion(
                model=self.models[0],
                messages=[{"role": "user", "content": full_prompt}],
                fallbacks=self.models[1:] if len(self.models) > 1 else None,
                num_retries=self.num_retries,
                timeout=self.timeout,
                max_tokens=150,
            )

            return self._parse_response(response.choices[0].message.content)

        except Exception as e:
            logger.warning(f"LiteLLM normalization error (all fallbacks failed): {e}")
            return NormalizationResult(
                wine_name=None,
                confidence=0.0,
                is_wine=False,
                reasoning=f"LLM error: {type(e).__name__}"
            )

    async def validate(
        self,
        ocr_text: str,
        db_candidate: Optional[str],
        db_rating: Optional[float]
    ) -> ValidationResult:
        """
        Validate if a DB candidate matches the OCR text using LiteLLM.

        Args:
            ocr_text: Raw OCR text from the bottle
            db_candidate: Candidate wine name from database fuzzy match
            db_rating: Rating of the DB candidate (for context)

        Returns:
            ValidationResult indicating if match is valid and correct wine name
        """
        if not ocr_text or len(ocr_text.strip()) < 3:
            return ValidationResult(
                is_valid_match=False,
                wine_name=None,
                confidence=0.0,
                reasoning="OCR text too short"
            )

        if not db_candidate:
            clean_name = _extract_clean_wine_name(ocr_text)
            return ValidationResult(
                is_valid_match=False,
                wine_name=clean_name,
                confidence=0.5 if clean_name else 0.0,
                reasoning="No DB candidate to validate"
            )

        if not LITELLM_AVAILABLE or not self.models:
            logger.debug("LiteLLM not available, using heuristic validation")
            return self._heuristic_validate(ocr_text, db_candidate)

        rating_str = f"{db_rating:.1f}" if db_rating else "unknown"
        user_prompt = f'OCR Text: "{ocr_text}"\nDB Candidate: "{db_candidate}" (rating: {rating_str})'
        full_prompt = f"{self.VALIDATION_PROMPT}\n\n{user_prompt}"

        try:
            litellm = _get_litellm()
            if not litellm:
                return self._heuristic_validate(ocr_text, db_candidate)
            response = await litellm.acompletion(
                model=self.models[0],
                messages=[{"role": "user", "content": full_prompt}],
                fallbacks=self.models[1:] if len(self.models) > 1 else None,
                num_retries=self.num_retries,
                timeout=self.timeout,
                max_tokens=150,
            )

            return self._parse_validation_response(
                response.choices[0].message.content,
                db_candidate
            )

        except Exception as e:
            logger.warning(f"LiteLLM validation error (all fallbacks failed): {e}")
            return self._heuristic_validate(ocr_text, db_candidate)

    async def validate_batch(
        self,
        items: list[BatchValidationItem]
    ) -> list[BatchValidationResult]:
        """
        Validate multiple OCR→DB matches in a single LLM call with automatic fallbacks.

        Args:
            items: List of BatchValidationItem with OCR text and DB candidates

        Returns:
            List of BatchValidationResult in the same order as input
        """
        if not items:
            return []

        if not LITELLM_AVAILABLE or not self.models:
            logger.debug("LiteLLM not available, using heuristic batch validation")
            return self._heuristic_validate_batch(items)

        items_text = self._format_batch_items(items)
        full_prompt = f"{self.BATCH_VALIDATION_PROMPT}\n\nItems to validate:\n{items_text}"

        try:
            litellm = _get_litellm()
            if not litellm:
                return self._heuristic_validate_batch(items)
            response = await litellm.acompletion(
                model=self.models[0],
                messages=[{"role": "user", "content": full_prompt}],
                fallbacks=self.models[1:] if len(self.models) > 1 else None,
                num_retries=self.num_retries,
                timeout=self.timeout,
                max_tokens=450 * len(items),  # Increased for expanded metadata + longer blurbs
            )

            return self._parse_batch_response(
                response.choices[0].message.content,
                items
            )

        except Exception as e:
            logger.warning(f"LiteLLM batch validation error (all fallbacks failed): {e}")
            return self._heuristic_validate_batch(items)


class MockNormalizer:
    """Mock normalizer for testing without API calls."""

    WINE_KEYWORDS = {
        'wine', 'cabernet', 'merlot', 'pinot', 'chardonnay', 'sauvignon',
        'blanc', 'syrah', 'zinfandel', 'riesling', 'noir', 'rose', 'rosé',
        'reserve', 'estate', 'vineyard', 'chateau', 'château', 'domaine',
        'valley', 'coast', 'sonoma', 'napa', 'burgundy', 'bordeaux',
        'tempranillo', 'malbec', 'shiraz', 'grenache', 'viognier',
    }

    NON_WINE_KEYWORDS = {
        'shelf', 'tag', 'price', 'sale', 'contains', 'sulfites',
        'warning', 'government', 'pregnant', 'surgeon',
    }

    async def normalize(
        self,
        ocr_text: str,
        context: Optional[dict] = None
    ) -> NormalizationResult:
        """Return mock normalization based on text content."""
        text_lower = ocr_text.lower()

        # Check for non-wine indicators first
        if any(kw in text_lower for kw in self.NON_WINE_KEYWORDS):
            return NormalizationResult(
                wine_name=None,
                confidence=0.0,
                is_wine=False,
                reasoning="Mock: Contains non-wine keywords"
            )

        # Check for wine keywords
        is_wine = any(kw in text_lower for kw in self.WINE_KEYWORDS)

        if is_wine:
            name = ocr_text.strip().title()
            return NormalizationResult(
                wine_name=name,
                confidence=0.75,
                is_wine=True,
                reasoning="Mock: Contains wine keywords"
            )

        return NormalizationResult(
            wine_name=None,
            confidence=0.0,
            is_wine=False,
            reasoning="Mock: No wine keywords found"
        )

    async def validate(
        self,
        ocr_text: str,
        db_candidate: Optional[str],
        db_rating: Optional[float]
    ) -> ValidationResult:
        """Mock validation - checks for obvious mismatches."""
        if not ocr_text:
            return ValidationResult(
                is_valid_match=False,
                wine_name=None,
                confidence=0.0,
                reasoning="Mock: No OCR text"
            )

        ocr_lower = ocr_text.lower().strip()
        db_lower = (db_candidate or "").lower().strip()

        # Check for obvious substring abuse (e.g., "Vennstone" vs "One")
        # If DB candidate is much shorter and not at start of OCR, reject
        if db_candidate and len(db_lower) < len(ocr_lower) * 0.5:
            if not ocr_lower.startswith(db_lower[:3]):
                clean_name = _extract_clean_wine_name(ocr_text)
                return ValidationResult(
                    is_valid_match=False,
                    wine_name=clean_name,
                    confidence=0.7 if clean_name else 0.0,
                    reasoning="Mock: DB candidate too short, likely substring match"
                )

        # Check if first word matches (producer name should match)
        ocr_first = ocr_lower.split()[0] if ocr_lower else ""
        db_first = db_lower.split()[0] if db_lower else ""

        if db_candidate and ocr_first and db_first:
            # If first words are very different, reject
            if ocr_first[:3] != db_first[:3] and db_first not in ocr_lower:
                clean_name = _extract_clean_wine_name(ocr_text)
                return ValidationResult(
                    is_valid_match=False,
                    wine_name=clean_name,
                    confidence=0.7 if clean_name else 0.0,
                    reasoning="Mock: Producer names don't match"
                )

        # Default: trust the match
        clean_name = _extract_clean_wine_name(ocr_text)
        return ValidationResult(
            is_valid_match=True,
            wine_name=db_candidate or clean_name,
            confidence=0.75,
            reasoning="Mock: Match appears valid"
        )

    async def validate_batch(
        self,
        items: list[BatchValidationItem]
    ) -> list[BatchValidationResult]:
        """
        Mock batch validation - validates each item using heuristics.

        Args:
            items: List of BatchValidationItem with OCR text and DB candidates

        Returns:
            List of BatchValidationResult in the same order as input
        """
        results = []
        for i, item in enumerate(items):
            validation = await self.validate(
                item.ocr_text,
                item.db_candidate,
                item.db_rating
            )
            # Mock: provide default rating for unmatched wines
            estimated_rating = None
            if not validation.is_valid_match or item.db_candidate is None:
                estimated_rating = 3.8  # Default mid-tier rating for mock
            results.append(BatchValidationResult(
                index=i,
                is_valid_match=validation.is_valid_match,
                wine_name=validation.wine_name,
                confidence=validation.confidence,
                reasoning=validation.reasoning,
                estimated_rating=estimated_rating
            ))
        return results


def get_normalizer(use_mock: bool = False) -> NormalizerProtocol:
    """
    Factory function for normalizers.

    Args:
        use_mock: If True, return mock normalizer for testing.

    Returns:
        A normalizer implementing NormalizerProtocol.
    """
    if use_mock:
        return MockNormalizer()

    if LITELLM_AVAILABLE:
        logger.info("Using LiteLLM for LLM normalization (automatic fallbacks enabled)")
        return LiteLLMNormalizer()
    else:
        logger.warning("LiteLLM not installed - LLM normalization disabled")
        return MockNormalizer()
