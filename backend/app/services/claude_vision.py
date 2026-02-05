"""
Claude Vision API service for wine identification from images.

This is the final fallback when OCR + fuzzy matching + LLM text normalization fails.
Sends the full shelf image to Claude Vision to identify wines at specific bottle locations.

Supports two modes:
1. Full image mode: Sends entire shelf image with bottle location hints (default)
2. Cropped mode: Sends individual cropped bottle images (more cost-effective)
"""

import base64
import io
import json
import logging
from dataclasses import dataclass
from typing import Optional

from PIL import Image

from ..config import Config
from .ocr_processor import BottleText
from .image_cropper import crop_multiple_bottles, NormalizedBBox

logger = logging.getLogger(__name__)

# Claude Vision API has a ~20MB limit, but we compress to 5MB for performance
CLAUDE_VISION_MAX_SIZE = 5 * 1024 * 1024  # 5MB


def _compress_image_for_vision(image_bytes: bytes, max_size: int = CLAUDE_VISION_MAX_SIZE) -> bytes:
    """
    Normalize image to JPEG and compress to fit within Claude Vision size limit.

    Always outputs JPEG to match the hardcoded media_type="image/jpeg" used
    when sending to the Anthropic API.

    Strategy:
    1. If already JPEG and under limit, return as-is (fast path)
    2. If non-JPEG (PNG, WebP, etc.), convert to JPEG
    3. If oversized, reduce JPEG quality (85 → 20)
    4. If still too large, resize progressively (80% → 30%)

    Args:
        image_bytes: Original image bytes
        max_size: Maximum size in bytes (default 5MB)

    Returns:
        Compressed image bytes (JPEG format)
    """
    # Fast path: already JPEG and under size limit
    is_jpeg = image_bytes[:2] == b'\xff\xd8'
    if is_jpeg and len(image_bytes) <= max_size:
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes))

    if not is_jpeg:
        logger.info(f"Converting {img.format or 'unknown'} image to JPEG for Claude Vision")

    if len(image_bytes) > max_size:
        logger.info(f"Compressing image for Claude Vision: {len(image_bytes) / 1024 / 1024:.1f}MB → target {max_size / 1024 / 1024:.1f}MB")

    # Convert to RGB if needed (JPEG doesn't support alpha)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Non-JPEG under size limit: just convert to JPEG at high quality
    if len(image_bytes) <= max_size:
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=95)
        return output.getvalue()

    # Try reducing quality first
    quality = 85
    while quality >= 20:
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=quality)
        compressed_size = output.tell()
        if compressed_size <= max_size:
            logger.info(f"Compressed with quality={quality}: {compressed_size / 1024 / 1024:.1f}MB")
            return output.getvalue()
        quality -= 15

    # If quality reduction wasn't enough, resize the image
    scale = 0.8
    while scale >= 0.3:
        new_size = (int(img.width * scale), int(img.height * scale))
        resized = img.resize(new_size, Image.Resampling.LANCZOS)
        output = io.BytesIO()
        resized.save(output, format="JPEG", quality=70)
        compressed_size = output.tell()
        if compressed_size <= max_size:
            logger.info(f"Resized to {new_size[0]}x{new_size[1]} (scale={scale:.1f}): {compressed_size / 1024 / 1024:.1f}MB")
            return output.getvalue()
        scale -= 0.1

    # Last resort: return whatever we have
    logger.warning(f"Could not compress image below {max_size / 1024 / 1024:.1f}MB, using {compressed_size / 1024 / 1024:.1f}MB")
    return output.getvalue()

# Try to import anthropic
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ModuleNotFoundError:
    anthropic = None  # type: ignore
    ANTHROPIC_AVAILABLE = False


@dataclass
class VisionIdentifiedWine:
    """A wine identified by Claude Vision."""
    bottle_index: int  # Index of the bottle in the input list
    wine_name: Optional[str]
    confidence: float  # 0.0-1.0
    estimated_rating: Optional[float]  # 0.0-5.0 if Claude can estimate
    wine_type: Optional[str]  # Red, White, Rosé, Sparkling
    brand: Optional[str]  # Winery/producer
    region: Optional[str]  # Wine region
    varietal: Optional[str]  # Grape variety
    blurb: Optional[str]  # 1-2 sentence description
    reasoning: str  # Why Claude identified this wine


def _build_single_bottle_prompt(ocr_hint: Optional[str] = None) -> str:
    """Build prompt for identifying a single cropped bottle image."""
    ocr_context = ""
    if ocr_hint:
        ocr_context = f"\n\nOCR text hint (may be partial or inaccurate): \"{ocr_hint[:100]}\""

    return f"""You are a wine expert. Identify the wine in this image of a single wine bottle.
{ocr_context}
Examine the label carefully and provide:
1. The wine name (producer + wine name, e.g. "Caymus Cabernet Sauvignon" or "Opus One")
2. Your confidence in the identification (0.0-1.0)
3. If you recognize this wine, estimate its rating (0.0-5.0 scale, like Vivino ratings)
4. Wine type (Red, White, Rose, Sparkling, Dessert, Fortified)
5. Producer/brand name
6. Region if identifiable
7. Grape variety if identifiable
8. A brief 1-sentence description if you know this wine

IMPORTANT:
- If you cannot identify the wine clearly, set wine_name to null and confidence to 0
- Do not guess wildly - only identify wines you can actually read or recognize
- Look for visual cues like distinctive artwork, logos, bottle shapes

Respond with a single JSON object:
{{
  "wine_name": "Producer Wine Name" or null,
  "confidence": 0.0-1.0,
  "estimated_rating": 0.0-5.0 or null,
  "wine_type": "Red|White|Rose|Sparkling|Dessert|Fortified" or null,
  "brand": "Producer name" or null,
  "region": "Region" or null,
  "varietal": "Grape variety" or null,
  "blurb": "Brief description" or null,
  "reasoning": "Why you identified this wine"
}}

Return ONLY the JSON object, no other text."""


def _build_vision_prompt(unmatched_bottles: list[BottleText]) -> str:
    """Build the prompt for Claude Vision."""
    # Describe the bottle locations
    bottle_descriptions = []
    for i, bt in enumerate(unmatched_bottles):
        bbox = bt.bottle.bbox
        # Convert normalized coords to percentage for readability
        x_pct = round(bbox.x * 100)
        y_pct = round(bbox.y * 100)
        w_pct = round(bbox.width * 100)
        h_pct = round(bbox.height * 100)

        ocr_hint = bt.combined_text[:100] if bt.combined_text else "no OCR text"
        bottle_descriptions.append(
            f"  Bottle {i}: Located at x={x_pct}%, y={y_pct}%, size {w_pct}%x{h_pct}%. "
            f"OCR hint: \"{ocr_hint}\""
        )

    bottles_text = "\n".join(bottle_descriptions)

    return f"""You are a wine expert analyzing a photo of a wine shelf. I need you to identify the wines at specific bottle locations.

The following bottles could not be identified through OCR and database matching. Please look at the image and identify each wine:

{bottles_text}

For each bottle, examine the label carefully and provide:
1. The wine name (producer + wine name, e.g. "Caymus Cabernet Sauvignon" or "Opus One")
2. Your confidence in the identification (0.0-1.0)
3. If you recognize this wine, estimate its rating (0.0-5.0 scale, like Vivino ratings)
4. Wine type (Red, White, Rosé, Sparkling, Dessert, Fortified)
5. Producer/brand name
6. Region if identifiable
7. Grape variety if identifiable
8. A brief 1-sentence description if you know this wine

Respond with a JSON array, one object per bottle in the same order as listed above.

IMPORTANT:
- If you cannot identify a bottle clearly, set wine_name to null and confidence to 0
- Do not guess wildly - only identify wines you can actually read or recognize
- The bottle indices must match exactly (0, 1, 2, etc.)

JSON Schema:
[
  {{
    "bottle_index": 0,
    "wine_name": "Producer Wine Name" or null,
    "confidence": 0.0-1.0,
    "estimated_rating": 0.0-5.0 or null,
    "wine_type": "Red|White|Rosé|Sparkling|Dessert|Fortified" or null,
    "brand": "Producer name" or null,
    "region": "Region" or null,
    "varietal": "Grape variety" or null,
    "blurb": "Brief description" or null,
    "reasoning": "Why you identified this wine"
  }}
]

Return ONLY the JSON array, no other text."""


def _parse_vision_response(response_text: str, num_bottles: int) -> list[VisionIdentifiedWine]:
    """Parse Claude's JSON response into VisionIdentifiedWine objects."""
    results = []

    try:
        # Extract JSON from response (handle markdown code blocks)
        json_text = response_text.strip()
        if json_text.startswith("```"):
            # Remove markdown code block
            lines = json_text.split("\n")
            json_text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])

        data = json.loads(json_text)

        if not isinstance(data, list):
            logger.error("Claude Vision response is not a list")
            return results

        for item in data:
            try:
                bottle_idx = item.get("bottle_index", -1)
                if bottle_idx < 0 or bottle_idx >= num_bottles:
                    continue

                results.append(VisionIdentifiedWine(
                    bottle_index=bottle_idx,
                    wine_name=item.get("wine_name"),
                    confidence=float(item.get("confidence", 0.0)),
                    estimated_rating=float(item["estimated_rating"]) if item.get("estimated_rating") is not None else None,
                    wine_type=item.get("wine_type"),
                    brand=item.get("brand"),
                    region=item.get("region"),
                    varietal=item.get("varietal"),
                    blurb=item.get("blurb"),
                    reasoning=item.get("reasoning", ""),
                ))
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Failed to parse bottle result: {e}")
                continue

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude Vision JSON response: {e}")
        logger.debug(f"Response was: {response_text[:500]}")

    return results


def _parse_single_bottle_response(response_text: str, bottle_index: int) -> Optional[VisionIdentifiedWine]:
    """Parse Claude's JSON response for a single bottle."""
    try:
        json_text = response_text.strip()
        if json_text.startswith("```"):
            lines = json_text.split("\n")
            json_text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])

        item = json.loads(json_text)

        if not isinstance(item, dict):
            logger.error("Claude Vision single bottle response is not a dict")
            return None

        return VisionIdentifiedWine(
            bottle_index=bottle_index,
            wine_name=item.get("wine_name"),
            confidence=float(item.get("confidence", 0.0)),
            estimated_rating=float(item["estimated_rating"]) if item.get("estimated_rating") is not None else None,
            wine_type=item.get("wine_type"),
            brand=item.get("brand"),
            region=item.get("region"),
            varietal=item.get("varietal"),
            blurb=item.get("blurb"),
            reasoning=item.get("reasoning", ""),
        )

    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        logger.error(f"Failed to parse single bottle response: {e}")
        return None


class ClaudeVisionService:
    """
    Service for identifying wines using Claude Vision API.

    Used as a final fallback when OCR + database matching fails.
    """

    # Model to use for vision - using Haiku for speed (3-5x faster than Sonnet)
    # Haiku is sufficient for reading wine labels and basic identification
    DEFAULT_MODEL = "claude-3-haiku-20240307"

    def __init__(
        self,
        model: Optional[str] = None,
        max_tokens: int = 2000,
        timeout: float = 30.0,
    ):
        """
        Initialize the Claude Vision service.

        Args:
            model: Claude model to use (default: claude-3-5-sonnet)
            max_tokens: Maximum tokens in response
            timeout: Request timeout in seconds
        """
        self.model = model or self.DEFAULT_MODEL
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._client: Optional["anthropic.Anthropic"] = None

    def _get_client(self) -> "anthropic.Anthropic":
        """Get or create Anthropic client."""
        if self._client is None:
            if not ANTHROPIC_AVAILABLE:
                raise RuntimeError("anthropic package not installed")

            api_key = Config.anthropic_api_key()
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY not configured")

            self._client = anthropic.Anthropic(
                api_key=api_key,
                timeout=self.timeout,
            )
        return self._client

    async def identify_wines(
        self,
        image_bytes: bytes,
        unmatched_bottles: list[BottleText],
        image_media_type: str = "image/jpeg",
    ) -> list[VisionIdentifiedWine]:
        """
        Identify wines at specific bottle locations using Claude Vision.

        Args:
            image_bytes: The full shelf image as bytes
            unmatched_bottles: List of bottles that couldn't be identified
            image_media_type: MIME type of the image

        Returns:
            List of VisionIdentifiedWine for successfully identified bottles
        """
        if not unmatched_bottles:
            return []

        if not ANTHROPIC_AVAILABLE:
            logger.warning("Claude Vision fallback unavailable: anthropic package not installed")
            return []

        api_key = Config.anthropic_api_key()
        if not api_key:
            logger.warning("Claude Vision fallback unavailable: ANTHROPIC_API_KEY not set")
            return []

        logger.info(f"Claude Vision: Attempting to identify {len(unmatched_bottles)} unmatched bottles")

        try:
            client = self._get_client()

            # Compress image if needed to stay under API limits
            compressed_bytes = _compress_image_for_vision(image_bytes)

            # Encode image to base64
            image_b64 = base64.standard_b64encode(compressed_bytes).decode("utf-8")

            # Build prompt
            prompt = _build_vision_prompt(unmatched_bottles)

            # Call Claude Vision API (sync call, wrapped for async compatibility)
            # Note: Using sync client for simplicity; could use async client if needed
            import asyncio
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": image_media_type,
                                        "data": image_b64,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": prompt,
                                },
                            ],
                        }
                    ],
                )
            )

            # Extract response text
            response_text = response.content[0].text if response.content else ""

            logger.debug(f"Claude Vision raw response: {response_text[:500]}...")

            # Parse response
            results = _parse_vision_response(response_text, len(unmatched_bottles))

            # Filter to wines that were actually identified
            identified = [r for r in results if r.wine_name and r.confidence > 0.3]

            logger.info(f"Claude Vision: Identified {len(identified)} of {len(unmatched_bottles)} bottles")
            for wine in identified:
                logger.debug(
                    f"  Bottle {wine.bottle_index}: {wine.wine_name} "
                    f"(conf={wine.confidence:.2f}, rating={wine.estimated_rating})"
                )

            return identified

        except Exception as e:
            logger.error(f"Claude Vision API error: {e}", exc_info=True)
            return []

    async def identify_wines_cropped(
        self,
        image_bytes: bytes,
        unmatched_bottles: list[BottleText],
    ) -> list[VisionIdentifiedWine]:
        """
        Identify wines using cropped individual bottle images.

        More cost-effective than sending full shelf image when there are
        few unmatched bottles. Each bottle is sent as a separate image.

        Args:
            image_bytes: The full shelf image as bytes
            unmatched_bottles: List of bottles that couldn't be identified

        Returns:
            List of VisionIdentifiedWine for successfully identified bottles
        """
        if not unmatched_bottles:
            return []

        if not ANTHROPIC_AVAILABLE:
            logger.warning("Claude Vision fallback unavailable: anthropic package not installed")
            return []

        api_key = Config.anthropic_api_key()
        if not api_key:
            logger.warning("Claude Vision fallback unavailable: ANTHROPIC_API_KEY not set")
            return []

        # Crop bottle regions
        bboxes = [
            NormalizedBBox(
                x=bt.bottle.bbox.x,
                y=bt.bottle.bbox.y,
                width=bt.bottle.bbox.width,
                height=bt.bottle.bbox.height,
            )
            for bt in unmatched_bottles
        ]

        crop_results = crop_multiple_bottles(image_bytes, bboxes)

        logger.info(f"Claude Vision (cropped): Processing {len(unmatched_bottles)} bottles")

        identified: list[VisionIdentifiedWine] = []

        try:
            client = self._get_client()
            import asyncio

            for idx, (bt, crop) in enumerate(zip(unmatched_bottles, crop_results)):
                if crop is None:
                    logger.warning(f"Skipping bottle {idx}: crop failed")
                    continue

                try:
                    # Build prompt with OCR hint
                    prompt = _build_single_bottle_prompt(bt.combined_text)

                    # Encode cropped image
                    image_b64 = base64.standard_b64encode(crop.image_bytes).decode("utf-8")

                    # Call Claude Vision
                    response = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda b64=image_b64, p=prompt: client.messages.create(
                            model=self.model,
                            max_tokens=500,  # Less tokens needed for single bottle
                            messages=[
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "image",
                                            "source": {
                                                "type": "base64",
                                                "media_type": "image/jpeg",
                                                "data": b64,
                                            },
                                        },
                                        {
                                            "type": "text",
                                            "text": p,
                                        },
                                    ],
                                }
                            ],
                        )
                    )

                    response_text = response.content[0].text if response.content else ""
                    result = _parse_single_bottle_response(response_text, idx)

                    if result and result.wine_name and result.confidence > 0.3:
                        identified.append(result)
                        logger.debug(
                            f"  Bottle {idx}: {result.wine_name} "
                            f"(conf={result.confidence:.2f}, rating={result.estimated_rating})"
                        )

                except Exception as e:
                    logger.warning(f"Failed to identify bottle {idx}: {e}")

            logger.info(f"Claude Vision (cropped): Identified {len(identified)} of {len(unmatched_bottles)} bottles")
            return identified

        except Exception as e:
            logger.error(f"Claude Vision API error (cropped mode): {e}", exc_info=True)
            return []


# Singleton instance
_claude_vision_service: Optional[ClaudeVisionService] = None


def get_claude_vision_service() -> ClaudeVisionService:
    """Get singleton ClaudeVisionService instance."""
    global _claude_vision_service
    if _claude_vision_service is None:
        _claude_vision_service = ClaudeVisionService()
    return _claude_vision_service
