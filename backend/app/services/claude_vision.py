"""
Claude Vision API for wine shelf analysis.

Replaces Google Cloud Vision API + LLM normalization with a single Claude call.
Benefits:
- Single API call instead of Vision API + LLM
- Better OCR accuracy for wine labels
- Direct wine name extraction (no separate normalization step)
- Simpler pipeline with fewer dependencies

Usage:
    service = ClaudeVisionService()
    result = service.analyze(image_bytes)
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from .vision import BoundingBox, DetectedObject, TextBlock, VisionResult, VisionServiceProtocol

logger = logging.getLogger(__name__)

# Try to import anthropic at module load time
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ModuleNotFoundError:
    anthropic = None  # type: ignore
    ANTHROPIC_AVAILABLE = False


@dataclass
class WineDetection:
    """Wine detected by Claude Vision."""
    wine_name: str                    # Extracted/normalized wine name
    raw_text: str                     # Raw OCR text from label
    position: str                     # Position description (e.g., "left", "center-top")
    confidence: float                 # Detection confidence (0-1)
    bbox: BoundingBox                 # Estimated bounding box


@dataclass
class ClaudeVisionResult:
    """Result from Claude Vision analysis."""
    wines: list[WineDetection]        # Detected wines with positions
    raw_ocr_text: str                 # Combined raw OCR text
    total_bottles: int                # Total bottles detected
    image_quality: str                # "good", "fair", "poor"
    # Compatible with VisionResult for downstream processing
    objects: list[DetectedObject]     # Bottle detections
    text_blocks: list[TextBlock]      # OCR text blocks


# Prompt for Claude Vision to analyze wine shelf images
WINE_SHELF_ANALYSIS_PROMPT = """Analyze this wine shelf image and extract all visible wine bottles.

For each wine bottle you can see:
1. Extract the wine name from the label (producer + varietal, e.g., "Caymus Cabernet Sauvignon")
2. Note the raw OCR text visible on the label
3. Estimate the bottle's position as normalized coordinates (0-1 range):
   - x: horizontal position (0=left edge, 1=right edge)
   - y: vertical position (0=top edge, 1=bottom edge)
   - width: bottle width as fraction of image
   - height: bottle height as fraction of image
4. Rate your confidence in the wine identification (0.0-1.0)

EXTRACTION RULES:
- Extract the canonical wine name (producer + varietal)
- REMOVE: vintage years (2019, 2021), bottle sizes (750ml), prices, ABV%, marketing text
- KEEP: Producer name, grape variety, region if part of the name
- If text is partially obscured, infer the likely wine name if possible

POSITION ESTIMATION:
- Divide the image into a grid and estimate bottle centers
- Typical wine bottle: width ~0.08-0.12, height ~0.30-0.40 of image
- Account for shelf perspective (bottles at edges may appear smaller)

Return ONLY valid JSON (no markdown, no explanation):
{
    "wines": [
        {
            "wine_name": "Producer Name Varietal",
            "raw_text": "PRODUCER NAME\\nVarietal\\n2021\\n750ml",
            "bbox": {"x": 0.15, "y": 0.20, "width": 0.10, "height": 0.35},
            "confidence": 0.92
        }
    ],
    "total_bottles": 5,
    "raw_ocr_text": "all visible text combined",
    "image_quality": "good"
}

Confidence scale:
- 0.90+: Clear, complete wine name visible
- 0.75-0.90: Partial but identifiable
- 0.60-0.75: Inferred from fragments
- <0.60: Very uncertain

If no wine bottles are visible, return:
{"wines": [], "total_bottles": 0, "raw_ocr_text": "", "image_quality": "poor"}"""


class ClaudeVisionService:
    """
    Wine shelf analyzer using Claude's vision capabilities.

    This service consolidates:
    - OCR (text extraction from labels)
    - Object detection (bottle identification)
    - Wine name normalization (LLM interpretation)

    Into a single API call, simplifying the pipeline.
    """

    # Use claude-3-5-sonnet for best vision accuracy, or claude-3-haiku for cost
    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    HAIKU_MODEL = "claude-3-5-haiku-20241022"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        use_haiku: bool = False
    ):
        """
        Initialize Claude Vision service.

        Args:
            api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
            model: Claude model to use. Defaults to claude-3-5-sonnet for accuracy.
            use_haiku: If True, use Haiku model for lower cost (less accurate).
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if model:
            self.model = model
        elif use_haiku:
            self.model = self.HAIKU_MODEL
        else:
            # Check for env override
            self.model = os.getenv("CLAUDE_VISION_MODEL", self.DEFAULT_MODEL)
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

    def analyze(self, image_bytes: bytes) -> VisionResult:
        """
        Analyze wine shelf image using Claude Vision.

        This method is compatible with VisionServiceProtocol, returning
        VisionResult for seamless integration with existing pipeline.

        Args:
            image_bytes: Raw image bytes (JPEG or PNG)

        Returns:
            VisionResult with detected bottles and text blocks
        """
        # Get detailed result first
        detailed = self.analyze_detailed(image_bytes)

        # Convert to VisionResult format for pipeline compatibility
        return VisionResult(
            objects=detailed.objects,
            text_blocks=detailed.text_blocks,
            raw_text=detailed.raw_ocr_text,
            image_width=1000,  # Normalized coordinates, no pixel dimensions needed
            image_height=1000
        )

    def analyze_detailed(self, image_bytes: bytes) -> ClaudeVisionResult:
        """
        Analyze wine shelf with full detail.

        Returns ClaudeVisionResult with wine names, positions, and confidence.
        Use this for direct wine identification without fuzzy matching.

        Args:
            image_bytes: Raw image bytes (JPEG or PNG)

        Returns:
            ClaudeVisionResult with detailed wine information
        """
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set, returning empty result")
            return self._empty_result()

        if not ANTHROPIC_AVAILABLE:
            logger.warning("anthropic module not installed, returning empty result")
            return self._empty_result()

        # Determine media type from image bytes
        media_type = self._detect_media_type(image_bytes)

        # Encode image as base64
        image_data = base64.standard_b64encode(image_bytes).decode("utf-8")

        try:
            client = self._get_client()

            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": WINE_SHELF_ANALYSIS_PROMPT
                            }
                        ],
                    }
                ],
            )

            # Parse response
            return self._parse_response(response.content[0].text)

        except anthropic.APIConnectionError as e:
            logger.error(f"Claude API connection failed: {e}")
            return self._empty_result()
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            return self._empty_result()
        except Exception as e:
            logger.error(f"Unexpected error in Claude Vision: {e}", exc_info=True)
            return self._empty_result()

    def _detect_media_type(self, image_bytes: bytes) -> str:
        """Detect image media type from bytes."""
        if image_bytes[:3] == b'\xff\xd8\xff':
            return "image/jpeg"
        elif image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        elif image_bytes[:4] == b'GIF8':
            return "image/gif"
        elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
            return "image/webp"
        else:
            # Default to JPEG
            return "image/jpeg"

    def _parse_response(self, response_text: str) -> ClaudeVisionResult:
        """Parse Claude's JSON response into ClaudeVisionResult."""
        try:
            # Handle potential markdown code blocks
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            data = json.loads(text)

            wines: list[WineDetection] = []
            objects: list[DetectedObject] = []
            text_blocks: list[TextBlock] = []

            for i, wine_data in enumerate(data.get("wines", [])):
                bbox_data = wine_data.get("bbox", {})
                bbox = BoundingBox(
                    x=float(bbox_data.get("x", 0.1 * (i + 1))),
                    y=float(bbox_data.get("y", 0.15)),
                    width=float(bbox_data.get("width", 0.08)),
                    height=float(bbox_data.get("height", 0.35))
                )

                confidence = float(wine_data.get("confidence", 0.75))
                wine_name = wine_data.get("wine_name", "")
                raw_text = wine_data.get("raw_text", wine_name)

                # Create WineDetection
                wines.append(WineDetection(
                    wine_name=wine_name,
                    raw_text=raw_text,
                    position=self._bbox_to_position(bbox),
                    confidence=confidence,
                    bbox=bbox
                ))

                # Create compatible DetectedObject (bottle)
                objects.append(DetectedObject(
                    name="Bottle",
                    confidence=confidence,
                    bbox=bbox
                ))

                # Create TextBlock with normalized wine name
                # This allows the pipeline to use Claude's already-normalized name
                text_blocks.append(TextBlock(
                    text=wine_name,  # Already normalized!
                    bbox=BoundingBox(
                        x=bbox.x,
                        y=bbox.y + bbox.height * 0.2,  # Position text in upper portion
                        width=bbox.width,
                        height=bbox.height * 0.15
                    ),
                    confidence=confidence
                ))

            return ClaudeVisionResult(
                wines=wines,
                raw_ocr_text=data.get("raw_ocr_text", ""),
                total_bottles=data.get("total_bottles", len(wines)),
                image_quality=data.get("image_quality", "fair"),
                objects=objects,
                text_blocks=text_blocks
            )

        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse Claude Vision response: {e}")
            logger.debug(f"Raw response: {response_text[:500]}")
            return self._empty_result()

    def _bbox_to_position(self, bbox: BoundingBox) -> str:
        """Convert bounding box to human-readable position."""
        # Horizontal position
        if bbox.x < 0.33:
            h_pos = "left"
        elif bbox.x < 0.66:
            h_pos = "center"
        else:
            h_pos = "right"

        # Vertical position
        if bbox.y < 0.33:
            v_pos = "top"
        elif bbox.y < 0.66:
            v_pos = "middle"
        else:
            v_pos = "bottom"

        if h_pos == "center" and v_pos == "middle":
            return "center"
        return f"{h_pos}-{v_pos}"

    def _empty_result(self) -> ClaudeVisionResult:
        """Return empty result for error cases."""
        return ClaudeVisionResult(
            wines=[],
            raw_ocr_text="",
            total_bottles=0,
            image_quality="poor",
            objects=[],
            text_blocks=[]
        )


class MockClaudeVisionService:
    """Mock Claude Vision service for testing."""

    def __init__(self, scenario: str = "full_shelf"):
        self.scenario = scenario

    def analyze(self, image_bytes: bytes) -> VisionResult:
        """Return mock VisionResult."""
        detailed = self.analyze_detailed(image_bytes)
        return VisionResult(
            objects=detailed.objects,
            text_blocks=detailed.text_blocks,
            raw_text=detailed.raw_ocr_text,
            image_width=1000,
            image_height=1000
        )

    def analyze_detailed(self, image_bytes: bytes) -> ClaudeVisionResult:
        """Return mock ClaudeVisionResult based on scenario."""
        if self.scenario == "full_shelf":
            return self._full_shelf_result()
        elif self.scenario == "partial":
            return self._partial_result()
        else:
            return self._empty_result()

    def _full_shelf_result(self) -> ClaudeVisionResult:
        """8 wines with mock data."""
        wines_data = [
            ("Caymus Cabernet Sauvignon", 0.05, 0.15, 0.95),
            ("Opus One", 0.15, 0.12, 0.93),
            ("Silver Oak Alexander Valley", 0.26, 0.14, 0.91),
            ("Jordan Cabernet Sauvignon", 0.36, 0.13, 0.89),
            ("Kendall-Jackson Vintner's Reserve", 0.46, 0.16, 0.87),
            ("La Crema Sonoma Coast Pinot Noir", 0.56, 0.14, 0.85),
            ("Meiomi Pinot Noir", 0.66, 0.15, 0.83),
            ("Bread & Butter Chardonnay", 0.76, 0.17, 0.80),
        ]

        wines = []
        objects = []
        text_blocks = []

        for name, x, y, conf in wines_data:
            bbox = BoundingBox(x=x, y=y, width=0.08, height=0.35)

            wines.append(WineDetection(
                wine_name=name,
                raw_text=name.upper(),
                position=f"x={x:.2f}",
                confidence=conf,
                bbox=bbox
            ))

            objects.append(DetectedObject(
                name="Bottle",
                confidence=conf,
                bbox=bbox
            ))

            text_blocks.append(TextBlock(
                text=name,
                bbox=BoundingBox(x=x, y=y + 0.07, width=0.08, height=0.05),
                confidence=conf
            ))

        return ClaudeVisionResult(
            wines=wines,
            raw_ocr_text=" | ".join([w.wine_name for w in wines]),
            total_bottles=len(wines),
            image_quality="good",
            objects=objects,
            text_blocks=text_blocks
        )

    def _partial_result(self) -> ClaudeVisionResult:
        """3 wines detected."""
        wines_data = [
            ("Caymus Cabernet Sauvignon", 0.10, 0.15, 0.94),
            ("Opus One", 0.30, 0.12, 0.91),
            ("Silver Oak Alexander Valley", 0.50, 0.14, 0.88),
        ]

        wines = []
        objects = []
        text_blocks = []

        for name, x, y, conf in wines_data:
            bbox = BoundingBox(x=x, y=y, width=0.10, height=0.35)

            wines.append(WineDetection(
                wine_name=name,
                raw_text=name.upper(),
                position=f"x={x:.2f}",
                confidence=conf,
                bbox=bbox
            ))

            objects.append(DetectedObject(
                name="Bottle",
                confidence=conf,
                bbox=bbox
            ))

            text_blocks.append(TextBlock(
                text=name,
                bbox=BoundingBox(x=x, y=y + 0.07, width=0.10, height=0.05),
                confidence=conf
            ))

        return ClaudeVisionResult(
            wines=wines,
            raw_ocr_text=" | ".join([w.wine_name for w in wines]),
            total_bottles=len(wines),
            image_quality="fair",
            objects=objects,
            text_blocks=text_blocks
        )

    def _empty_result(self) -> ClaudeVisionResult:
        """No wines detected."""
        return ClaudeVisionResult(
            wines=[],
            raw_ocr_text="",
            total_bottles=0,
            image_quality="poor",
            objects=[],
            text_blocks=[]
        )


def get_vision_service(
    provider: str = "google",
    use_mock: bool = False,
    mock_scenario: str = "full_shelf",
    **kwargs
) -> VisionServiceProtocol:
    """
    Factory function for vision services.

    Args:
        provider: Vision provider ("google" or "claude")
        use_mock: If True, return mock service for testing
        mock_scenario: Mock scenario (full_shelf, partial, empty)
        **kwargs: Additional arguments passed to the service

    Returns:
        A vision service implementing VisionServiceProtocol
    """
    if provider.lower() == "claude":
        if use_mock:
            return MockClaudeVisionService(scenario=mock_scenario)
        return ClaudeVisionService(**kwargs)
    else:
        # Default to Google Vision
        from .vision import VisionService, MockVisionService
        if use_mock:
            return MockVisionService(scenario=mock_scenario)
        return VisionService()
