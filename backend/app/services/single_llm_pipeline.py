"""
Single-LLM wine recognition pipeline.

One multimodal LLM call per scan. The model detects every visible bottle, reads
its label, identifies the wine, estimates a Vivino-style rating, and returns a
bounding box — all in a single structured response.

Replaces the multi-stage Vision-API + Gemini-Flash + Hungarian-merge pipeline.
There is no fallback to legacy pipelines; on LLM failure the caller surfaces
the error.

Default model: anthropic/claude-haiku-4-5-20251001 (override via SINGLE_LLM_MODEL).
Any LiteLLM-supported multimodal model works — Haiku, Sonnet, Opus, Gemini 2.5 Pro, etc.
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
from .llm_usage import log_usage
from .ocr_processor import BottleText
from .recognition_pipeline import RecognizedWine
from .vision import BoundingBox as VisionBBox, DetectedObject
from .wine_matcher import WineMatcher

# Lazy import for litellm to avoid network calls during module load.
_litellm = None
_litellm_checked = False

logger = logging.getLogger(__name__)

# Anthropic's API caps base64-encoded images at 5 MB. Base64 inflates raw bytes
# by ~33%, so we cap raw bytes at ~3.6 MB to leave headroom.
# Other providers (Gemini, OpenAI) have higher limits, so this is the
# conservative budget that works across all supported models.
_LLM_IMAGE_RAW_BUDGET = int(5 * 1024 * 1024 * 0.72)


def _get_litellm():
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
class SingleLLMWine:
    """A wine identified by the single-LLM pipeline call."""
    wine_name: Optional[str]
    confidence: float
    estimated_rating: Optional[float]
    bbox: dict  # {x, y, width, height} normalized 0-1
    vintage: Optional[str] = None
    wine_type: Optional[str] = None
    brand: Optional[str] = None
    region: Optional[str] = None
    varietal: Optional[str] = None
    blurb: Optional[str] = None


@dataclass
class SingleLLMResult:
    """Result from the single-LLM pipeline."""
    recognized_wines: list[RecognizedWine]
    raw_llm_wines: list[SingleLLMWine]
    timings: dict


SINGLE_LLM_PROMPT = """You are a wine expert analyzing a photo of a wine shelf or wine display.

Your job: identify EVERY wine bottle visible in the image, including bottles in back rows and partially occluded bottles. Be exhaustive — if there are 14 bottles, return 14 entries.

For each bottle return:
1. A bounding box as normalized coordinates (0-1): x, y, width, height where (x,y) is the top-left corner. The bbox should tightly fit the bottle (cap to base) so a rating overlay anchored to the upper-third of the bbox lands on the label.
2. wine_name: "Producer Wine Name" (e.g., "Caymus Cabernet Sauvignon", "Opus One"). Set to null only if the label is unreadable.
3. vintage: 4-digit year as a STRING (e.g., "2021") if visible on the label, otherwise null. Do NOT guess vintages — only return a year you can clearly read. Non-vintage products (NV champagnes, generic table wines) should return null.
4. confidence: your confidence in the identification, 0.0-1.0.
5. estimated_rating: Vivino 1-5 scale (1.0-2.9 = poor, 3.0-3.4 = average, 3.5-3.9 = good, 4.0-4.4 = very good, 4.5-5.0 = outstanding). Default to 3.7-4.0 if uncertain.
6. wine_type, brand, region, varietal: optional short metadata fields.

RULES:
- Do NOT skip back-row or occluded bottles. Return a bbox for every visible bottle.
- Do NOT hallucinate wine names you cannot read. Set wine_name to null if unreadable.
- Bounding boxes must be tight to the bottle, not to the shelf or surrounding area.

OUTPUT RULES (strict):
- Return ONLY the JSON array. No preamble, no explanation, no markdown.
- Do NOT wrap in ```json fences. Do NOT add commentary before or after.
- First character of your response MUST be '['. Last character MUST be ']'.

Schema:
[
  {
    "wine_name": "Producer Wine Name" or null,
    "vintage": "2021" or null,
    "confidence": 0.0-1.0,
    "estimated_rating": 1.0-5.0 or null,
    "bbox": {"x": 0.0-1.0, "y": 0.0-1.0, "width": 0.0-1.0, "height": 0.0-1.0},
    "wine_type": "Red|White|Rosé|Sparkling|Dessert|Fortified" or null,
    "brand": "Producer name" or null,
    "region": "Region" or null,
    "varietal": "Grape variety" or null
  }
]"""


def _parse_llm_response(response_text: str) -> list[SingleLLMWine]:
    """Parse LLM JSON response into SingleLLMWine objects."""
    text = response_text.strip()

    # Strip markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"SingleLLMPipeline: Failed to parse LLM response: {e}")
        logger.debug(f"Response was: {response_text[:500]}")
        return []

    if not isinstance(data, list):
        logger.error("SingleLLMPipeline: LLM response is not a JSON array")
        return []

    results: list[SingleLLMWine] = []
    for item in data:
        if not isinstance(item, dict):
            continue

        wine_name = item.get("wine_name")
        if wine_name is None:
            # Skip unidentified bottles — they can't carry useful overlays anyway.
            continue

        bbox_raw = item.get("bbox", {}) or {}
        if not isinstance(bbox_raw, dict):
            bbox_raw = {}
        bbox = {
            "x": float(bbox_raw.get("x", 0)),
            "y": float(bbox_raw.get("y", 0)),
            "width": float(bbox_raw.get("width", 0)),
            "height": float(bbox_raw.get("height", 0)),
        }

        estimated_rating = item.get("estimated_rating")
        if estimated_rating is not None:
            estimated_rating = float(estimated_rating)
            estimated_rating = max(1.0, min(5.0, estimated_rating))

        vintage_raw = item.get("vintage")
        vintage = str(vintage_raw).strip() if vintage_raw else None
        if vintage and not vintage.isdigit():
            # Reject non-numeric vintages defensively — model occasionally emits
            # things like "NV" instead of null.
            vintage = None

        confidence = float(item.get("confidence", 0.5))

        results.append(SingleLLMWine(
            wine_name=str(wine_name).strip(),
            confidence=confidence,
            estimated_rating=estimated_rating,
            bbox=bbox,
            vintage=vintage,
            wine_type=item.get("wine_type"),
            brand=item.get("brand"),
            region=item.get("region"),
            varietal=item.get("varietal"),
            blurb=item.get("blurb"),
        ))

    return results


class SingleLLMPipeline:
    """
    One multimodal LLM call per scan. Detects, reads, and identifies every
    visible wine bottle in a single round-trip; cross-references results
    against the wine DB for canonical names + authoritative ratings.

    No fallback. If the LLM call fails, the exception propagates so the
    route can surface it to the client.
    """

    def __init__(
        self,
        wine_matcher: Optional[WineMatcher] = None,
        use_llm_cache: Optional[bool] = None,
        model: Optional[str] = None,
        # 2500 proved too small on dense shelves (20-40 bottles): the JSON
        # array truncates mid-stream, fails to parse, and the scan returns
        # ZERO results. Measured 2026-07-04: 8/10 corpus images truncated.
        max_tokens: int = 8000,
        temperature: float = 0.1,
    ):
        self.wine_matcher = wine_matcher or WineMatcher()
        self._configured_model = model  # explicit override; None = use Config
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._executor = ThreadPoolExecutor(max_workers=4)

        cache_enabled = use_llm_cache if use_llm_cache is not None else Config.use_llm_cache()
        self._llm_cache: Optional[LLMRatingCache] = get_llm_rating_cache() if cache_enabled else None

    def _select_model(self) -> str:
        """Resolve which model to use for this scan.

        Single-model implementation. Subclasses or tests may override to
        implement programmatic selection (e.g. route by image size), but
        each individual scan still uses exactly one model.
        """
        return self._configured_model or Config.single_llm_model()

    async def scan(
        self,
        image_bytes: bytes,
        image_media_type: str = "image/jpeg",
        image_id: str = "",
    ) -> SingleLLMResult:
        """
        Run the single-LLM pipeline.

        `image_id` is forwarded into the per-call token-usage record so
        cost can be correlated back to a specific scan request.

        Raises whatever the LLM call raises; callers must handle.
        """
        timings: dict = {}
        total_start = time.perf_counter()
        model = self._select_model()
        timings["model"] = model

        t0 = time.perf_counter()
        llm_wines = await self._call_llm(image_bytes, image_media_type, model, image_id)
        timings["llm_call_ms"] = round((time.perf_counter() - t0) * 1000)
        logger.info(
            f"SingleLLMPipeline: {model} identified {len(llm_wines)} wines "
            f"in {timings['llm_call_ms']}ms"
        )

        if not llm_wines:
            timings["total_ms"] = round((time.perf_counter() - total_start) * 1000)
            return SingleLLMResult(
                recognized_wines=[],
                raw_llm_wines=[],
                timings=timings,
            )

        t0 = time.perf_counter()
        recognized_wines = self._match_against_db(llm_wines)
        timings["db_lookup_ms"] = round((time.perf_counter() - t0) * 1000)
        logger.info(
            f"SingleLLMPipeline: DB matched "
            f"{sum(1 for w in recognized_wines if w.source == WineSource.DATABASE)} "
            f"of {len(recognized_wines)} wines in {timings['db_lookup_ms']}ms"
        )

        t0 = time.perf_counter()
        self._cache_llm_wines(recognized_wines, model)
        timings["cache_ms"] = round((time.perf_counter() - t0) * 1000)

        timings["total_ms"] = round((time.perf_counter() - total_start) * 1000)
        logger.info(
            f"SingleLLMPipeline: Total {timings['total_ms']}ms "
            f"(LLM={timings['llm_call_ms']}ms, DB={timings['db_lookup_ms']}ms, "
            f"cache={timings['cache_ms']}ms)"
        )

        return SingleLLMResult(
            recognized_wines=recognized_wines,
            raw_llm_wines=llm_wines,
            timings=timings,
        )

    async def _call_llm(
        self,
        image_bytes: bytes,
        image_media_type: str,
        model: str,
        image_id: str,
    ) -> list[SingleLLMWine]:
        litellm = _get_litellm()
        if litellm is None:
            raise RuntimeError(
                "SingleLLMPipeline: litellm is not installed. "
                "Install it with `pip install litellm` to enable the pipeline."
            )

        compressed = _compress_image_for_vision(image_bytes, max_size=_LLM_IMAGE_RAW_BUDGET)
        image_b64 = base64.b64encode(compressed).decode("utf-8")
        # _compress_image_for_vision always emits JPEG.
        media_type = "image/jpeg"

        kwargs = dict(
            model=model,
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
                            "text": SINGLE_LLM_PROMPT,
                        },
                    ],
                }
            ],
            max_tokens=self.max_tokens,
            drop_params=True,
        )
        # Anthropic deprecated `temperature` for Opus 4.7+ (returns 400 if
        # passed). Keep it for older models where it still tightens determinism.
        if "opus-4-7" not in model:
            kwargs["temperature"] = self.temperature

        # Time only the network round-trip — base64 + image compression are
        # local CPU work and don't belong in the latency_ms field used for
        # provider cost/perf analysis.
        api_start = time.perf_counter()
        response = await litellm.acompletion(**kwargs)
        api_latency_ms = round((time.perf_counter() - api_start) * 1000)

        # Pull usage off the response. Some providers / mocks omit it.
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        cached_tokens = None
        prompt_details = getattr(usage, "prompt_tokens_details", None) if usage else None
        if prompt_details is not None:
            cached_tokens = getattr(prompt_details, "cached_tokens", None)

        # Truncation canary: if the response spent ≥ 95% of the output budget,
        # the JSON is probably cut mid-array and the parser will silently drop
        # entries. Surface it (warning + flag in the usage record) so we can
        # bump max_tokens before users notice.
        truncated = (
            isinstance(completion_tokens, (int, float))
            and completion_tokens >= self.max_tokens * 0.95
        )
        if truncated:
            logger.warning(
                "SingleLLMPipeline: response near max_tokens (%d/%d) — "
                "possible truncation. Consider raising max_tokens.",
                completion_tokens,
                self.max_tokens,
            )

        if prompt_tokens is not None or completion_tokens is not None:
            log_usage(
                image_id=image_id,
                model=model,
                prompt_tokens=int(prompt_tokens) if prompt_tokens is not None else None,
                completion_tokens=int(completion_tokens) if completion_tokens is not None else None,
                cached_tokens=int(cached_tokens) if cached_tokens is not None else None,
                latency_ms=api_latency_ms,
                truncated=bool(truncated),
                log_path=Config.token_usage_log_path(),
            )

        response_text = response.choices[0].message.content
        return _parse_llm_response(response_text)

    def _match_against_db(
        self,
        llm_wines: list[SingleLLMWine],
    ) -> list[RecognizedWine]:
        """
        Cross-reference LLM-identified wines against the database.

        DB match with confidence ≥ 0.80 wins: use DB canonical name + DB rating.
        Otherwise fall back to LLM name + LLM-estimated rating, with capped
        confidence so non-DB wines never get top-3 emphasis.
        """
        def lookup(wine: SingleLLMWine) -> RecognizedWine:
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

            db_match = self.wine_matcher.match(wine.wine_name)

            if db_match and db_match.confidence >= 0.80:
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
                    vintage=wine.vintage,
                    wine_id=db_match.wine_id,
                )

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
                vintage=wine.vintage,
            )

        futures = [self._executor.submit(lookup, wine) for wine in llm_wines]
        results: list[RecognizedWine] = []
        for future in futures:
            try:
                results.append(future.result())
            except Exception as e:
                logger.error(f"SingleLLMPipeline: DB lookup failed: {e}", exc_info=True)

        return results

    def _cache_llm_wines(self, recognized_wines: list[RecognizedWine], model: str) -> None:
        """Persist LLM-identified wines (not in DB) to the rating cache."""
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
                llm_provider=model,
                wine_type=wine.wine_type,
                region=wine.region,
                varietal=wine.varietal,
                brand=wine.brand,
                blurb=wine.blurb,
                vintage=wine.vintage,
            )
