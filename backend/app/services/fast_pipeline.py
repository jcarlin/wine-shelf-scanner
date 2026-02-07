"""
Fast single-pass wine recognition pipeline using Gemini Flash Vision.

Replaces the 5-stage sequential pipeline (Vision API -> OCR -> fuzzy match ->
LLM validate -> Claude Vision -> LLM rescue) with:
1. Single Gemini 2.0 Flash multimodal call (detect + identify + estimate ratings)
2. Parallel DB lookups for authoritative ratings
3. Cache results in llm_ratings_cache

Expected latency: 2-4s total vs 8-14s for the original pipeline.
"""

import base64
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

from ..config import Config
from ..models.enums import RatingSource, WineSource
from .claude_vision import _compress_image_for_vision
from .llm_rating_cache import get_llm_rating_cache, LLMRatingCache
from .ocr_processor import BottleText
from .recognition_pipeline import RecognizedWine
from .vision import BoundingBox as VisionBBox, DetectedObject
from .wine_matcher import WineMatcher, WineMatch

# Lazy import for litellm to avoid slow network requests during module load
_litellm = None
_litellm_checked = False

logger = logging.getLogger(__name__)


def _get_litellm():
    """Lazy-load litellm to avoid startup delays from network requests."""
    global _litellm, _litellm_checked
    if not _litellm_checked:
        _litellm_checked = True
        try:
            import litellm
            litellm.set_verbose = False
            _litellm = litellm
        except ModuleNotFoundError:
            _litellm = None
    return _litellm


@dataclass
class FastPipelineWine:
    """A wine identified by the fast pipeline LLM call."""
    wine_name: Optional[str]
    confidence: float
    estimated_rating: Optional[float]
    bbox: dict  # {x, y, width, height} normalized 0-1
    wine_type: Optional[str] = None
    brand: Optional[str] = None
    region: Optional[str] = None
    varietal: Optional[str] = None
    blurb: Optional[str] = None


@dataclass
class FastPipelineResult:
    """Result from the fast pipeline."""
    recognized_wines: list[RecognizedWine]
    raw_llm_wines: list[FastPipelineWine]
    timings: dict  # Stage timing breakdown


FAST_PIPELINE_PROMPT = """You are a wine expert analyzing a photo of a wine shelf. Identify ALL wine bottles visible in the image.

For each bottle, provide:
1. Its bounding box as normalized coordinates (0-1 range): x, y, width, height where (x,y) is the top-left corner
2. The wine name as "Producer Wine Name" (e.g., "Caymus Cabernet Sauvignon", "Opus One")
3. Your confidence in the identification (0.0-1.0)
4. An estimated rating on the Vivino 1-5 scale
5. Wine type, brand, region, varietal, and a brief tasting note

RULES:
- If you cannot identify a bottle, set wine_name to null
- Do NOT guess wildly — only identify wines you can read or recognize
- Bounding boxes should tightly fit each bottle
- Use the Vivino scale: 1.0-2.9 = poor, 3.0-3.4 = average, 3.5-3.9 = good, 4.0-4.4 = very good, 4.5-5.0 = outstanding
- Default to 3.7-4.0 if uncertain about rating

Return a JSON array (no markdown, no extra text):
[
  {
    "wine_name": "Producer Wine Name" or null,
    "confidence": 0.0-1.0,
    "estimated_rating": 1.0-5.0 or null,
    "bbox": {"x": 0.0-1.0, "y": 0.0-1.0, "width": 0.0-1.0, "height": 0.0-1.0},
    "wine_type": "Red|White|Rosé|Sparkling|Dessert|Fortified" or null,
    "brand": "Producer name" or null,
    "region": "Region" or null,
    "varietal": "Grape variety" or null,
    "blurb": "One sentence tasting note" or null
  }
]"""


def _parse_llm_response(response_text: str) -> list[FastPipelineWine]:
    """Parse LLM JSON response into FastPipelineWine objects."""
    text = response_text.strip()

    # Strip markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```)
        lines = lines[1:]
        # Remove last line if it's closing ```
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"FastPipeline: Failed to parse LLM response: {e}")
        logger.debug(f"Response was: {response_text[:500]}")
        return []

    if not isinstance(data, list):
        logger.error("FastPipeline: LLM response is not a JSON array")
        return []

    results = []
    for item in data:
        if not isinstance(item, dict):
            continue

        wine_name = item.get("wine_name")
        if wine_name is None:
            continue

        # Parse bbox
        bbox_raw = item.get("bbox", {})
        if not isinstance(bbox_raw, dict):
            bbox_raw = {}

        bbox = {
            "x": float(bbox_raw.get("x", 0)),
            "y": float(bbox_raw.get("y", 0)),
            "width": float(bbox_raw.get("width", 0)),
            "height": float(bbox_raw.get("height", 0)),
        }

        # Parse rating
        estimated_rating = item.get("estimated_rating")
        if estimated_rating is not None:
            estimated_rating = float(estimated_rating)
            estimated_rating = max(1.0, min(5.0, estimated_rating))

        confidence = float(item.get("confidence", 0.5))

        results.append(FastPipelineWine(
            wine_name=wine_name,
            confidence=confidence,
            estimated_rating=estimated_rating,
            bbox=bbox,
            wine_type=item.get("wine_type"),
            brand=item.get("brand"),
            region=item.get("region"),
            varietal=item.get("varietal"),
            blurb=item.get("blurb"),
        ))

    return results


class FastPipeline:
    """
    Single-pass wine recognition using Gemini Flash Vision.

    Flow:
    1. Send image to Gemini Flash with multimodal prompt
    2. LLM detects bottles, identifies wines, estimates ratings in one call
    3. Cross-reference identified wines against DB for authoritative ratings
    4. Cache LLM-identified wines not in DB
    """

    def __init__(
        self,
        wine_matcher: Optional[WineMatcher] = None,
        use_llm_cache: Optional[bool] = None,
        model: Optional[str] = None,
        max_tokens: int = 4000,
        temperature: float = 0.1,
    ):
        self.wine_matcher = wine_matcher or WineMatcher()
        self.model = model or f"gemini/{Config.gemini_model()}"
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._executor = ThreadPoolExecutor(max_workers=4)

        cache_enabled = use_llm_cache if use_llm_cache is not None else Config.use_llm_cache()
        self._llm_cache: Optional[LLMRatingCache] = get_llm_rating_cache() if cache_enabled else None

    async def scan(
        self,
        image_bytes: bytes,
        image_media_type: str = "image/jpeg",
    ) -> FastPipelineResult:
        """
        Run the fast single-pass pipeline.

        Args:
            image_bytes: Raw image bytes
            image_media_type: MIME type of the image

        Returns:
            FastPipelineResult with recognized wines and timing data
        """
        timings = {}
        total_start = time.perf_counter()

        # Stage 1: Gemini Flash Vision call
        t0 = time.perf_counter()
        llm_wines = await self._call_gemini_vision(image_bytes, image_media_type)
        timings["llm_call_ms"] = round((time.perf_counter() - t0) * 1000)
        logger.info(
            f"FastPipeline: Gemini identified {len(llm_wines)} wines "
            f"in {timings['llm_call_ms']}ms"
        )

        if not llm_wines:
            timings["total_ms"] = round((time.perf_counter() - total_start) * 1000)
            return FastPipelineResult(
                recognized_wines=[],
                raw_llm_wines=[],
                timings=timings,
            )

        # Stage 2: Parallel DB lookups
        t0 = time.perf_counter()
        recognized_wines = self._match_against_db(llm_wines)
        timings["db_lookup_ms"] = round((time.perf_counter() - t0) * 1000)
        logger.info(
            f"FastPipeline: DB matched {sum(1 for w in recognized_wines if w.source == WineSource.DATABASE)} "
            f"of {len(recognized_wines)} wines in {timings['db_lookup_ms']}ms"
        )

        # Stage 3: Cache LLM-only wines
        t0 = time.perf_counter()
        self._cache_llm_wines(recognized_wines)
        timings["cache_ms"] = round((time.perf_counter() - t0) * 1000)

        timings["total_ms"] = round((time.perf_counter() - total_start) * 1000)
        logger.info(
            f"FastPipeline: Total {timings['total_ms']}ms "
            f"(LLM={timings['llm_call_ms']}ms, DB={timings['db_lookup_ms']}ms, "
            f"cache={timings['cache_ms']}ms)"
        )

        return FastPipelineResult(
            recognized_wines=recognized_wines,
            raw_llm_wines=llm_wines,
            timings=timings,
        )

    async def _call_gemini_vision(
        self,
        image_bytes: bytes,
        image_media_type: str,
    ) -> list[FastPipelineWine]:
        """Send image to Gemini Flash and parse response."""
        litellm = _get_litellm()
        if not litellm:
            logger.error("FastPipeline: litellm not available")
            return []

        # Compress image for API limits
        compressed = _compress_image_for_vision(image_bytes)
        image_b64 = base64.b64encode(compressed).decode("utf-8")

        # Always send as JPEG since _compress_image_for_vision outputs JPEG
        media_type = "image/jpeg"

        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{image_b64}",
                                },
                            },
                            {
                                "type": "text",
                                "text": FAST_PIPELINE_PROMPT,
                            },
                        ],
                    }
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            response_text = response.choices[0].message.content
            return _parse_llm_response(response_text)

        except Exception as e:
            logger.error(f"FastPipeline: Gemini Vision call failed: {e}", exc_info=True)
            return []

    def _match_against_db(
        self,
        llm_wines: list[FastPipelineWine],
    ) -> list[RecognizedWine]:
        """
        Cross-reference LLM-identified wines against the database.

        Uses ThreadPoolExecutor for parallel DB lookups.
        DB match with confidence >= 0.80 uses the DB rating.
        LLM-only wines get capped confidence.
        """
        def lookup(wine: FastPipelineWine) -> RecognizedWine:
            # Create a synthetic BottleText from LLM bbox
            bottle_text = BottleText(
                bottle=DetectedObject(
                    name="Bottle",
                    confidence=wine.confidence,
                    bbox=VisionBBox(
                        x=wine.bbox.get("x", 0),
                        y=wine.bbox.get("y", 0),
                        width=wine.bbox.get("width", 0),
                        height=wine.bbox.get("height", 0),
                    ),
                ),
                text_fragments=[wine.wine_name],
                combined_text=wine.wine_name,
                normalized_name=wine.wine_name,
            )

            # Try DB match
            db_match = self.wine_matcher.match(wine.wine_name)

            if db_match and db_match.confidence >= 0.80:
                # Use DB wine + authoritative rating
                return RecognizedWine(
                    wine_name=db_match.canonical_name,
                    rating=db_match.rating,
                    confidence=min(wine.confidence, db_match.confidence),
                    source=WineSource.DATABASE,
                    identified=True,
                    bottle_text=bottle_text,
                    rating_source=RatingSource.DATABASE,
                    wine_type=db_match.wine_type or wine.wine_type,
                    brand=db_match.brand or wine.brand,
                    region=db_match.region or wine.region,
                    varietal=db_match.varietal or wine.varietal,
                    blurb=wine.blurb,
                    wine_id=db_match.wine_id,
                )
            else:
                # LLM-only wine — cap confidence
                rating = wine.estimated_rating
                if rating is not None:
                    capped_confidence = min(wine.confidence, 0.75)
                    rating_source = RatingSource.LLM_ESTIMATED
                else:
                    capped_confidence = min(wine.confidence, 0.65)
                    rating_source = RatingSource.NONE

                return RecognizedWine(
                    wine_name=wine.wine_name,
                    rating=rating,
                    confidence=capped_confidence,
                    source=WineSource.LLM,
                    identified=True,
                    bottle_text=bottle_text,
                    rating_source=rating_source,
                    wine_type=wine.wine_type,
                    brand=wine.brand,
                    region=wine.region,
                    varietal=wine.varietal,
                    blurb=wine.blurb,
                )

        # Parallel DB lookups
        futures = [self._executor.submit(lookup, wine) for wine in llm_wines]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except Exception as e:
                logger.error(f"FastPipeline: DB lookup failed: {e}", exc_info=True)

        return results

    def _cache_llm_wines(self, recognized_wines: list[RecognizedWine]) -> None:
        """Cache LLM-identified wines not in DB for future lookups."""
        if not self._llm_cache:
            return

        for wine in recognized_wines:
            if wine.source != WineSource.LLM:
                continue
            if wine.rating is None:
                continue
            if len(wine.wine_name) > 80 or len(wine.wine_name.split()) > 10:
                continue

            self._llm_cache.set(
                wine_name=wine.wine_name,
                estimated_rating=wine.rating,
                confidence=wine.confidence,
                llm_provider=self.model,
                wine_type=wine.wine_type,
                region=wine.region,
                varietal=wine.varietal,
                brand=wine.brand,
                blurb=wine.blurb,
            )
