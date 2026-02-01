"""
LLM-based OCR text normalization for wine labels.

Uses Claude Haiku for cost-effective normalization of messy OCR text
to canonical wine names. Swappable via the NormalizerProtocol.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional, Protocol

# Try to import anthropic at module load time (for type hints and availability check)
# but don't make any API calls without proper configuration
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ModuleNotFoundError:
    anthropic = None  # type: ignore
    ANTHROPIC_AVAILABLE = False

# Try to import google.genai for Gemini support (new unified SDK)
try:
    from google import genai
    GEMINI_AVAILABLE = True
except ModuleNotFoundError:
    genai = None  # type: ignore
    GEMINI_AVAILABLE = False

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

    Subclasses only need to implement:
    - normalize(): API-specific LLM call for normalization
    - validate(): API-specific LLM call for validation
    - validate_batch(): API-specific batched validation
    - _get_client(): Lazy load the LLM client
    """

    # Subclasses should override these prompts if needed
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
- Clean up the name (remove years, sizes, marketing text)

## RATING ESTIMATION

For wines NOT in our database (when db_candidate is null or match is invalid):
- Provide an estimated_rating (1.0-5.0) based on your wine knowledge
- Consider: producer reputation, region quality, varietal typicity, price tier indicators
- Use this scale:
  - 4.5-5.0: Prestigious/cult wines (Opus One, Screaming Eagle, top Burgundy)
  - 4.0-4.5: Well-regarded producers with good track record
  - 3.5-4.0: Solid everyday wines from known regions
  - 3.0-3.5: Budget wines or unknown producers
  - Below 3.0: Only for wines with known quality issues
- Default to 3.7-4.0 if uncertain (typical mid-tier wine)

## OUTPUT

Return a JSON array with one result per input item (same order):
[
  {"index": 0, "is_valid_match": true, "wine_name": "...", "confidence": 0.95, "reasoning": "..."},
  {"index": 1, "is_valid_match": false, "wine_name": "Correct Name", "confidence": 0.85, "reasoning": "...", "estimated_rating": 4.2},
  ...
]

Include estimated_rating ONLY when is_valid_match is false or db_candidate was null."""

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

                    results.append(BatchValidationResult(
                        index=i,
                        is_valid_match=bool(result_data.get("is_valid_match", False)),
                        wine_name=result_data.get("wine_name") or item.db_candidate,
                        confidence=float(result_data.get("confidence", 0.5)),
                        reasoning=result_data.get("reasoning", ""),
                        estimated_rating=estimated_rating
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


class ClaudeNormalizer(LLMNormalizerBase):
    """
    Wine name normalizer using Claude Haiku.

    Cost: ~$0.001 per call (input ~200 tokens, output ~50 tokens)

    Inherits shared parsing/validation logic from LLMNormalizerBase.
    """

    MODEL = "claude-3-haiku-20240307"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize normalizer.

        Args:
            api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._client = None

    def _get_client(self):
        """Lazy load Anthropic client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY not set. Set env var or pass api_key."
                )
            if not ANTHROPIC_AVAILABLE:
                raise ModuleNotFoundError("anthropic module not installed")
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    async def normalize(
        self,
        ocr_text: str,
        context: Optional[dict] = None
    ) -> NormalizationResult:
        """
        Normalize OCR text to canonical wine name.

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

        # Early return if API key not configured (don't even try to import)
        if not self.api_key:
            logger.debug("ANTHROPIC_API_KEY not set, skipping LLM normalization")
            return NormalizationResult(
                wine_name=None,
                confidence=0.0,
                is_wine=False,
                reasoning="LLM not configured"
            )

        # Build prompt
        user_prompt = f'OCR Text: "{ocr_text}"'
        if context:
            user_prompt += f"\nContext: {json.dumps(context)}"
        user_prompt += """

Return JSON: {"wine_name": "...", "confidence": 0.0-1.0, "is_wine": true/false, "reasoning": "..."}"""

        # Check if anthropic is available before making API calls
        if not ANTHROPIC_AVAILABLE:
            logger.warning("anthropic module not installed, skipping LLM normalization")
            return NormalizationResult(
                wine_name=None,
                confidence=0.0,
                is_wine=False,
                reasoning="LLM not available"
            )

        try:
            client = self._get_client()

            # Use sync client in async wrapper (Anthropic SDK handles this)
            response = client.messages.create(
                model=self.MODEL,
                max_tokens=150,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}]
            )

            # Parse response
            return self._parse_response(response.content[0].text)

        except anthropic.APIConnectionError as e:
            logger.warning(f"Anthropic API connection failed: {e}")
            return NormalizationResult(
                wine_name=None,
                confidence=0.0,
                is_wine=False,
                reasoning="LLM service unavailable"
            )
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            return NormalizationResult(
                wine_name=None,
                confidence=0.0,
                is_wine=False,
                reasoning="LLM service error"
            )
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return NormalizationResult(
                wine_name=None,
                confidence=0.0,
                is_wine=False,
                reasoning="Failed to parse LLM response"
            )
        except ValueError as e:
            # API key not set
            logger.warning(f"LLM configuration error: {e}")
            return NormalizationResult(
                wine_name=None,
                confidence=0.0,
                is_wine=False,
                reasoning="LLM not configured"
            )
        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(f"Unexpected LLM error: {e}", exc_info=True)
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
        Validate if a DB candidate matches the OCR text.

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

        # If no DB candidate, just try to identify the wine
        if not db_candidate:
            clean_name = _extract_clean_wine_name(ocr_text)
            return ValidationResult(
                is_valid_match=False,
                wine_name=clean_name,
                confidence=0.5 if clean_name else 0.0,
                reasoning="No DB candidate to validate"
            )

        # Use heuristic validation if LLM not available
        if not self.api_key or not ANTHROPIC_AVAILABLE:
            logger.debug("LLM not available, using heuristic validation")
            return self._heuristic_validate(ocr_text, db_candidate)

        # Build prompt for LLM validation
        rating_str = f"{db_rating:.1f}" if db_rating else "unknown"
        user_prompt = f'OCR Text: "{ocr_text}"\nDB Candidate: "{db_candidate}" (rating: {rating_str})'

        try:
            client = self._get_client()

            response = client.messages.create(
                model=self.MODEL,
                max_tokens=150,
                system=self.VALIDATION_PROMPT,
                messages=[{"role": "user", "content": user_prompt}]
            )

            return self._parse_validation_response(response.content[0].text, db_candidate)

        except Exception as e:
            logger.warning(f"LLM validation error: {e}")
            # On error, use heuristic validation
            return self._heuristic_validate(ocr_text, db_candidate)

    async def validate_batch(
        self,
        items: list[BatchValidationItem]
    ) -> list[BatchValidationResult]:
        """
        Validate multiple OCR→DB matches in a single LLM call.

        This is more efficient than individual validate() calls when processing
        multiple bottles, reducing API overhead and latency.

        Args:
            items: List of BatchValidationItem with OCR text and DB candidates

        Returns:
            List of BatchValidationResult in the same order as input
        """
        if not items:
            return []

        # Fall back to heuristic validation if LLM not available
        if not self.api_key or not ANTHROPIC_AVAILABLE:
            logger.debug("LLM not available, using heuristic batch validation")
            return self._heuristic_validate_batch(items)

        # Build batch prompt
        items_text = self._format_batch_items(items)
        user_prompt = f"Items to validate:\n{items_text}"

        try:
            client = self._get_client()

            response = client.messages.create(
                model=self.MODEL,
                max_tokens=150 * len(items),  # Scale with batch size
                system=self.BATCH_VALIDATION_PROMPT,
                messages=[{"role": "user", "content": user_prompt}]
            )

            return self._parse_batch_response(response.content[0].text, items)

        except Exception as e:
            logger.warning(f"LLM batch validation error: {e}")
            return self._heuristic_validate_batch(items)


class GeminiNormalizer(LLMNormalizerBase):
    """
    Wine name normalizer using Google Gemini.

    Cost: ~$0.0001 per call with gemini-2.0-flash (very cheap)

    Inherits shared parsing/validation logic and prompts from LLMNormalizerBase.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize normalizer.

        Args:
            api_key: Google API key. Falls back to GOOGLE_API_KEY env var.
            model: Gemini model name. Falls back to GEMINI_MODEL env var.
        """
        from ..config import Config
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model = model or Config.gemini_model()
        self._client = None

    def _get_client(self):
        """Lazy load Gemini client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "GOOGLE_API_KEY not set. Set env var or pass api_key."
                )
            if not GEMINI_AVAILABLE:
                raise ModuleNotFoundError("google-genai module not installed")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def normalize(
        self,
        ocr_text: str,
        context: Optional[dict] = None
    ) -> NormalizationResult:
        """
        Normalize OCR text to canonical wine name.

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

        # Early return if API key not configured
        if not self.api_key:
            logger.debug("GOOGLE_API_KEY not set, skipping LLM normalization")
            return NormalizationResult(
                wine_name=None,
                confidence=0.0,
                is_wine=False,
                reasoning="LLM not configured"
            )

        # Build prompt
        user_prompt = f'OCR Text: "{ocr_text}"'
        if context:
            user_prompt += f"\nContext: {json.dumps(context)}"
        user_prompt += """

Return JSON: {"wine_name": "...", "confidence": 0.0-1.0, "is_wine": true/false, "reasoning": "..."}"""

        # Check if genai is available before making API calls
        if not GEMINI_AVAILABLE:
            logger.warning("google-genai module not installed, skipping LLM normalization")
            return NormalizationResult(
                wine_name=None,
                confidence=0.0,
                is_wine=False,
                reasoning="LLM not available"
            )

        try:
            client = self._get_client()

            # Combine system prompt with user prompt for Gemini
            full_prompt = f"{self.SYSTEM_PROMPT}\n\n{user_prompt}"

            response = client.models.generate_content(
                model=self.model,
                contents=full_prompt
            )

            # Parse response (using inherited method from base class)
            return self._parse_response(response.text)

        except Exception as e:
            logger.warning(f"Gemini API error: {e}")
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
        Validate if a DB candidate matches the OCR text.

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

        # If no DB candidate, just try to identify the wine
        if not db_candidate:
            clean_name = _extract_clean_wine_name(ocr_text)
            return ValidationResult(
                is_valid_match=False,
                wine_name=clean_name,
                confidence=0.5 if clean_name else 0.0,
                reasoning="No DB candidate to validate"
            )

        # Use heuristic validation if LLM not available
        if not self.api_key or not GEMINI_AVAILABLE:
            logger.debug("LLM not available, using heuristic validation")
            return self._heuristic_validate(ocr_text, db_candidate)

        # Build prompt for LLM validation
        rating_str = f"{db_rating:.1f}" if db_rating else "unknown"
        user_prompt = f'OCR Text: "{ocr_text}"\nDB Candidate: "{db_candidate}" (rating: {rating_str})'

        try:
            client = self._get_client()

            # Combine system prompt with user prompt for Gemini
            full_prompt = f"{self.VALIDATION_PROMPT}\n\n{user_prompt}"

            response = client.models.generate_content(
                model=self.model,
                contents=full_prompt
            )

            return self._parse_validation_response(response.text, db_candidate)

        except Exception as e:
            logger.warning(f"Gemini validation error: {e}")
            # On error, use heuristic validation (inherited from base class)
            return self._heuristic_validate(ocr_text, db_candidate)

    async def validate_batch(
        self,
        items: list[BatchValidationItem]
    ) -> list[BatchValidationResult]:
        """
        Validate multiple OCR→DB matches in a single LLM call.

        Args:
            items: List of BatchValidationItem with OCR text and DB candidates

        Returns:
            List of BatchValidationResult in the same order as input
        """
        if not items:
            return []

        if not self.api_key or not GEMINI_AVAILABLE:
            logger.debug("LLM not available, using heuristic batch validation")
            return self._heuristic_validate_batch(items)

        items_text = self._format_batch_items(items)
        full_prompt = f"{self.BATCH_VALIDATION_PROMPT}\n\nItems to validate:\n{items_text}"

        try:
            client = self._get_client()

            response = client.models.generate_content(
                model=self.model,
                contents=full_prompt
            )

            # Parse batch response (using inherited method from base class)
            return self._parse_batch_response(response.text, items)

        except Exception as e:
            logger.warning(f"Gemini batch validation error: {e}")
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


def get_normalizer(use_mock: bool = False, provider: str = "claude") -> NormalizerProtocol:
    """
    Factory function for normalizers.

    Args:
        use_mock: If True, return mock normalizer for testing.
        provider: LLM provider to use ("claude" or "gemini"). Default: "claude".

    Returns:
        A normalizer implementing NormalizerProtocol.
    """
    if use_mock:
        return MockNormalizer()
    if provider.lower() == "gemini":
        logger.info("Using Gemini for LLM normalization")
        return GeminiNormalizer()
    logger.info("Using Claude for LLM normalization")
    return ClaudeNormalizer()
