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

logger = logging.getLogger(__name__)


@dataclass
class NormalizationResult:
    """Result from LLM normalization."""
    wine_name: Optional[str]  # Canonical name or None if not parseable
    confidence: float         # 0.0-1.0
    is_wine: bool             # True if this appears to be a wine label
    reasoning: str            # Brief explanation


class NormalizerProtocol(Protocol):
    """Protocol for wine name normalizers (allows swapping LLM providers)."""
    async def normalize(
        self,
        ocr_text: str,
        context: Optional[dict] = None
    ) -> NormalizationResult: ...


class ClaudeNormalizer:
    """
    Wine name normalizer using Claude Haiku.

    Cost: ~$0.001 per call (input ~200 tokens, output ~50 tokens)
    """

    MODEL = "claude-3-haiku-20240307"

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

    def _parse_response(self, response_text: str) -> NormalizationResult:
        """Parse LLM JSON response."""
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
    return ClaudeNormalizer()
