"""
/scan endpoint for Wine Shelf Scanner.

Receives an image and returns wine detection results.
Uses tiered recognition pipeline: fuzzy match → LLM fallback.
"""

import io
import logging
import time
import uuid
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from PIL import Image
from pillow_heif import register_heif_opener

from ..config import Config
from ..feature_flags import FeatureFlags, get_feature_flags
from ..mocks.fixtures import get_mock_response
from ..models import BoundingBox, DebugData, FallbackWine, RatingSourceDetail, ScanResponse, WineResult
from ..models.debug import PipelineStats
from ..models.enums import RatingSource, WineSource
from ..services.claude_vision import get_claude_vision_service, VisionIdentifiedWine
from ..services.llm_rating_cache import get_llm_rating_cache
from ..services.ocr_processor import BottleText, OCRProcessor, OCRProcessingResult, OrphanedText, extract_wine_names
from ..services.pairing import PairingService
from ..services.recognition_pipeline import RecognizedWine, RecognitionPipeline
from ..services.llm_normalizer import BatchValidationItem, get_normalizer
from ..services.vision import MockVisionService, ReplayVisionService, VisionResult, VisionService
from ..services.wine_matcher import WineMatcher, _is_llm_generic_response
from ..services.fast_pipeline import FastPipeline
from ..services.wine_sync import sync_discovered_wines

logger = logging.getLogger(__name__)
router = APIRouter()


def _vision_to_recognized(
    vision_wine: VisionIdentifiedWine,
    bottle_text: BottleText
) -> RecognizedWine:
    """Convert Claude Vision result to RecognizedWine.

    Vision results get special handling:
    - Confidence floor at VISION_CONFIDENCE_FLOOR (0.65) to ensure tappability
    - Confidence cap at VISION_FALLBACK_CONFIDENCE_CAP (0.70) to avoid top-3 emphasis
    - Default rating of VISION_DEFAULT_RATING (3.5) when Claude can't estimate
    """
    # Floor at tappable threshold, cap to avoid top-3 emphasis
    capped_confidence = max(
        Config.VISION_CONFIDENCE_FLOOR,
        min(vision_wine.confidence, Config.VISION_FALLBACK_CONFIDENCE_CAP)
    )

    # Use estimated rating or default to neutral rating if Claude couldn't estimate
    rating = vision_wine.estimated_rating if vision_wine.estimated_rating is not None else Config.VISION_DEFAULT_RATING
    has_estimated_rating = vision_wine.estimated_rating is not None

    return RecognizedWine(
        wine_name=vision_wine.wine_name,
        rating=rating,
        confidence=capped_confidence,
        source=WineSource.VISION,
        identified=True,
        bottle_text=bottle_text,
        rating_source=RatingSource.LLM_ESTIMATED if has_estimated_rating else RatingSource.DEFAULT,
        wine_type=vision_wine.wine_type,
        brand=vision_wine.brand,
        region=vision_wine.region,
        varietal=vision_wine.varietal,
        blurb=vision_wine.blurb,
    )


def _to_wine_result(wine: RecognizedWine) -> WineResult:
    """Convert RecognizedWine to WineResult for API response."""
    return WineResult(
        wine_name=wine.wine_name,
        wine_id=wine.wine_id,
        rating=wine.rating,
        confidence=wine.confidence,
        bbox=BoundingBox(
            x=wine.bottle_text.bottle.bbox.x,
            y=wine.bottle_text.bottle.bbox.y,
            width=wine.bottle_text.bottle.bbox.width,
            height=wine.bottle_text.bottle.bbox.height
        ),
        identified=wine.identified,
        source=wine.source,
        rating_source=wine.rating_source,
        wine_type=wine.wine_type,
        brand=wine.brand,
        region=wine.region,
        varietal=wine.varietal,
        blurb=wine.blurb,
        review_count=wine.review_count,
        review_snippets=wine.review_snippets,
    )


def _process_orphaned_texts(
    orphaned_texts: list[OrphanedText],
    wine_matcher: WineMatcher
) -> list[FallbackWine]:
    """
    Process orphaned text blocks through wine matcher.

    Orphaned texts are OCR text blocks not assigned to any detected bottle.
    They may contain wine names from bottles the Vision API failed to detect.

    Args:
        orphaned_texts: List of OrphanedText with normalized wine name candidates
        wine_matcher: Wine matcher for fuzzy matching

    Returns:
        List of FallbackWine for wines matched from orphaned text
    """
    matches = []
    seen_names = set()

    for orphan in orphaned_texts:
        if not orphan.normalized_name or len(orphan.normalized_name) < 3:
            continue

        # Skip if we've already matched this name
        name_lower = orphan.normalized_name.lower()
        if name_lower in seen_names:
            continue

        # Try to match against wine database
        match = wine_matcher.match(orphan.normalized_name)
        if match and match.rating is not None:
            # Only add if confidence is reasonable (avoid false positives)
            if match.confidence >= 0.60:
                matches.append(FallbackWine(
                    wine_name=match.canonical_name,
                    rating=match.rating
                ))
                seen_names.add(name_lower)
                seen_names.add(match.canonical_name.lower())

    return matches


# === Feature flag helpers ===

# Safe pick heuristic: common crowd-pleaser varietals
_SAFE_VARIETALS = {
    "cabernet sauvignon", "merlot", "pinot noir", "chardonnay",
    "sauvignon blanc", "pinot grigio", "pinot gris", "syrah", "shiraz",
    "malbec", "riesling", "tempranillo", "zinfandel", "rosé",
    "sangiovese", "grenache",
}

_pairing_service = PairingService()

# Maps source_name in DB to human-readable display name
_SOURCE_DISPLAY_NAMES = {
    "vivino": "Vivino",
    "kaggle_wine_reviews": "Wine Enthusiast",
    "wine_enthusiast": "Wine Enthusiast",
    "wine_spectator": "Wine Spectator",
    "cellartracker": "CellarTracker",
    "robert_parker": "Robert Parker",
    "james_suckling": "James Suckling",
    "decanter": "Decanter",
}


def _get_rating_source_details(wine_name: str, wine_matcher: WineMatcher) -> Optional[list[RatingSourceDetail]]:
    """Look up rating source details for a wine from wine_sources table."""
    if wine_matcher._repository is None:
        return None
    result = wine_matcher._repository.find_by_name_with_id(wine_name)
    if not result:
        return None
    _record, wine_id = result
    sources = wine_matcher._repository.get_rating_sources(wine_id)
    if not sources:
        return None
    details = []
    for src in sources:
        scale_max = src["scale_max"]
        scale_label = f"/ {int(scale_max)}" if scale_max == int(scale_max) else f"/ {scale_max}"
        details.append(RatingSourceDetail(
            source_name=src["source_name"],
            display_name=_SOURCE_DISPLAY_NAMES.get(src["source_name"], src["source_name"].replace("_", " ").title()),
            original_rating=src["original_rating"],
            scale_label=scale_label,
        ))
    return details


def _enrich_with_reviews(recognized: list[RecognizedWine], wine_matcher: WineMatcher) -> None:
    """Enrich recognized wines with actual review text from wine_reviews table.

    For DB-matched wines with a wine_id, fetches review stats (count) and
    review text snippets from the wine_reviews table. Only overrides
    review_snippets if actual text reviews are found; otherwise preserves
    any existing description-based snippets.
    """
    if wine_matcher._repository is None:
        return

    repo = wine_matcher._repository
    for wine in recognized:
        if wine.wine_id is None:
            continue

        # Get review stats (total count)
        stats = repo.get_review_stats(wine.wine_id)
        if stats['total_reviews'] > 0:
            wine.review_count = stats['total_reviews']

        # Fetch actual review text (up to 3 snippets)
        reviews = repo.get_reviews(wine.wine_id, limit=3, text_only=True)
        if reviews:
            snippets = [r.review_text for r in reviews if r.review_text]
            if snippets:
                wine.review_snippets = snippets


def _apply_feature_flags(results: list[WineResult], flags: FeatureFlags, wine_matcher: Optional[WineMatcher] = None) -> None:
    """Apply feature-flagged enrichments to scan results (mutates in place)."""
    for result in results:
        if flags.feature_pairings:
            result.pairing = _pairing_service.get_pairing(result.varietal, result.wine_type)

        if flags.feature_safe_pick:
            result.is_safe_pick = _compute_safe_pick(result)

        if flags.feature_trust_signals and wine_matcher:
            result.rating_sources = _get_rating_source_details(result.wine_name, wine_matcher)


def _compute_safe_pick(wine: WineResult) -> bool:
    """Determine if a wine qualifies as a 'safe pick' (crowd favorite).

    Uses heuristic: high rating + high confidence + common varietal.
    When review_count data is available in the DB, this should be updated
    to use review_count >= 500 as a primary signal.
    """
    if wine.rating is None or wine.rating < 4.0:
        return False
    if wine.confidence < 0.85:
        return False
    # Only trust database ratings for safe pick designation
    if wine.rating_source not in (RatingSource.DATABASE, None):
        return False
    # Check if varietal is a common crowd-pleaser
    varietal = (wine.varietal or "").lower()
    if varietal and varietal in _SAFE_VARIETALS:
        return True
    # Fallback: high-rated wines from well-known types still qualify
    wine_type = (wine.wine_type or "").lower()
    if wine_type in ("red", "white") and wine.rating >= 4.2:
        return True
    return False


# Register HEIF/HEIC opener with Pillow
register_heif_opener()


# === Image Conversion ===


def convert_heic_to_jpeg(image_bytes: bytes, content_type: str) -> bytes:
    """
    Convert HEIC/HEIF images to JPEG. Pass through other formats unchanged.

    Args:
        image_bytes: Raw image bytes
        content_type: MIME type of the image

    Returns:
        JPEG bytes if HEIC/HEIF, otherwise original bytes
    """
    if content_type not in ("image/heic", "image/heif"):
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes))

    # Convert to RGB (HEIC may have alpha channel)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    output = io.BytesIO()
    img.save(output, format="JPEG", quality=90)
    return output.getvalue()


# === Dependency Injection ===


@lru_cache(maxsize=1)
def get_wine_matcher() -> WineMatcher:
    """Get or create wine matcher instance (singleton via lru_cache)."""
    return WineMatcher(use_sqlite=Config.use_sqlite())


def get_pipeline(use_llm: bool = True, debug_mode: bool = False) -> RecognitionPipeline:
    """Create recognition pipeline with specified LLM setting."""
    return RecognitionPipeline(
        wine_matcher=get_wine_matcher(),
        use_llm=use_llm,
        llm_provider=Config.llm_provider(),
        debug_mode=debug_mode
    )


# === Endpoints ===


@router.post("/scan", response_model=ScanResponse)
async def scan_shelf(
    image: UploadFile = File(..., description="Wine shelf image"),
    mock_scenario: Optional[str] = Query(None, description="Mock scenario for testing"),
    use_vision_api: bool = Query(True, description="Use real Vision API"),
    use_llm: bool = Query(True, description="Use LLM fallback for unknown wines"),
    use_vision_fallback: bool = Query(True, description="Use Claude Vision for unmatched bottles"),
    debug: bool = Query(default=None, description="Include pipeline debug info in response"),
    use_vision_fixture: Optional[str] = Query(None, description="Path to captured Vision API response fixture for replay"),
    wine_matcher: WineMatcher = Depends(get_wine_matcher),
    flags: FeatureFlags = Depends(get_feature_flags),
) -> ScanResponse:
    """
    Scan a wine shelf image and return detected wines with ratings.

    Args:
        image: The shelf image (JPEG or PNG)
        mock_scenario: Optional fixture name for testing (full_shelf, partial_detection, etc.)
        use_vision_api: Whether to use real Google Vision API (requires credentials)
        use_llm: Whether to use LLM fallback for OCR normalization

    Returns:
        ScanResponse with detected wines and fallback list
    """
    # Validate content type
    if image.content_type not in Config.ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid image type. Only JPEG and PNG are supported."
        )

    # Generate unique image ID
    image_id = str(uuid.uuid4())

    # Check if we should use mocks
    use_mocks = Config.use_mocks()

    if mock_scenario:
        # Explicit mock scenario requested
        return get_mock_response(image_id, mock_scenario)

    if use_mocks and not use_vision_api:
        # Default to mock response
        return get_mock_response(image_id, "full_shelf")

    # Read and validate image
    try:
        image_bytes = await image.read()
    except IOError as e:
        logger.error(f"Failed to read uploaded image: {e}")
        raise HTTPException(status_code=400, detail="Failed to read image file")

    # Convert HEIC/HEIF to JPEG
    image_bytes = convert_heic_to_jpeg(image_bytes, image.content_type)

    # Validate file size
    if len(image_bytes) > Config.MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Maximum size is {Config.MAX_IMAGE_SIZE_MB}MB."
        )

    # Resolve debug mode: query param overrides env var
    debug_mode = debug if debug is not None else Config.debug_mode()

    # Process image
    try:
        return await process_image(
            image_id, image_bytes, use_vision_api, use_llm, use_vision_fallback, debug_mode, wine_matcher, flags, use_vision_fixture
        )
    except ValueError as e:
        logger.warning(f"Invalid image format: {e}")
        raise HTTPException(status_code=400, detail="Invalid image format")
    except Exception as e:
        logger.error(f"Unexpected error processing image: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


async def _run_fast_pipeline(
    image_id: str,
    image_bytes: bytes,
    debug_mode: bool,
    wine_matcher: WineMatcher,
    flags: Optional[FeatureFlags] = None,
) -> Optional[ScanResponse]:
    """Run single-pass multimodal LLM pipeline.

    Returns ScanResponse on success, or None if no results were found
    (allowing fallback to legacy pipeline when Config.fast_pipeline_fallback() is True).
    """
    t0 = time.perf_counter()

    pipeline = FastPipeline(
        wine_matcher=wine_matcher,
        model=f"gemini/{Config.fast_pipeline_model()}",
    )
    result = await pipeline.scan(image_bytes)
    recognized = result.recognized_wines

    if not recognized:
        elapsed = time.perf_counter() - t0
        logger.info(f"[{image_id}] Fast pipeline returned 0 results in {elapsed:.2f}s")
        if Config.fast_pipeline_fallback():
            return None
        # No fallback — return empty response
        return ScanResponse(image_id=image_id, results=[], fallback_list=[])

    # Enrich with review data
    _enrich_with_reviews(recognized, wine_matcher)

    # Deduplicate by wine name (keep highest confidence)
    seen_wines: dict[str, RecognizedWine] = {}
    for wine in recognized:
        name_key = wine.wine_name.lower().strip()
        if name_key not in seen_wines or wine.confidence > seen_wines[name_key].confidence:
            seen_wines[name_key] = wine
    recognized = list(seen_wines.values())

    # Build results and fallback lists
    results: list[WineResult] = []
    fallback: list[FallbackWine] = []

    for wine in recognized:
        if wine.confidence >= Config.VISIBILITY_THRESHOLD:
            results.append(_to_wine_result(wine))
        elif wine.rating is not None:
            fallback.append(FallbackWine(
                wine_name=wine.wine_name,
                rating=wine.rating,
            ))

    # Sort by rating descending
    results.sort(key=lambda x: (x.rating is not None, x.rating or 0), reverse=True)
    fallback.sort(key=lambda x: x.rating, reverse=True)

    # Apply feature flags
    if flags:
        _apply_feature_flags(results, flags, wine_matcher=wine_matcher)

    # Sync discovered wines back to DB
    sync_discovered_wines(results, fallback)

    elapsed = time.perf_counter() - t0
    logger.info(
        f"[{image_id}] Fast pipeline completed in {elapsed:.2f}s: "
        f"{len(results)} results, {len(fallback)} fallback"
    )

    return ScanResponse(
        image_id=image_id,
        results=results,
        fallback_list=fallback,
    )


async def process_image(
    image_id: str,
    image_bytes: bytes,
    use_real_api: bool,
    use_llm: bool,
    use_vision_fallback: bool,
    debug_mode: bool,
    wine_matcher: WineMatcher,
    flags: Optional[FeatureFlags] = None,
    vision_fixture: Optional[str] = None,
) -> ScanResponse:
    """
    Tiered recognition pipeline:
    1. Vision API (object detection + OCR)
    2. OCR grouping (text → bottle assignment)
    3. Enhanced fuzzy matching (rapidfuzz + phonetic)
    4. LLM fallback for low-confidence/unknown wines
    5. Response construction
    """
    # === Fast Pipeline Branch ===
    if Config.use_fast_pipeline():
        try:
            fast_result = await _run_fast_pipeline(
                image_id, image_bytes, debug_mode, wine_matcher, flags
            )
            if fast_result is not None:
                return fast_result
            logger.info(f"[{image_id}] Fast pipeline returned no results, falling back to legacy")
        except Exception as e:
            logger.warning(f"[{image_id}] Fast pipeline failed: {e}")
            if not Config.fast_pipeline_fallback():
                raise
            logger.info(f"[{image_id}] Falling back to legacy pipeline")

    # Choose vision service
    if vision_fixture:
        # Use captured fixture for deterministic replay
        vision_service = ReplayVisionService(vision_fixture)
        logger.info(f"[{image_id}] Using vision fixture: {vision_fixture}")
    elif use_real_api:
        vision_service = VisionService()
    else:
        vision_service = MockVisionService("full_shelf")

    # === Pipeline Stats Collection ===
    # Track where bottles are lost at each stage
    stats_bottles_detected = 0
    stats_bottles_with_text = 0
    stats_bottles_empty = 0
    stats_fuzzy_matched = 0
    stats_llm_validated = 0
    stats_unmatched_count = 0
    stats_vision_attempted = 0
    stats_vision_identified = 0
    stats_vision_error: Optional[str] = None

    # Step 1: Analyze image
    vision_result = vision_service.analyze(image_bytes)
    stats_bottles_detected = len(vision_result.objects)
    logger.info(f"[{image_id}] BOTTLES DETECTED: {stats_bottles_detected}")

    # Log individual bottle bboxes in debug mode
    if Config.debug_mode():
        for i, obj in enumerate(vision_result.objects):
            logger.debug(f"[{image_id}]   Bottle {i}: bbox=({obj.bbox.x:.2f},{obj.bbox.y:.2f},{obj.bbox.width:.2f}x{obj.bbox.height:.2f}) conf={obj.confidence:.2f}")

    if Config.debug_mode():
        logger.debug(f"[{image_id}] Raw OCR: {vision_result.raw_text[:500] if vision_result.raw_text else 'None'}...")

    if not vision_result.objects:
        # No bottles detected - try matching raw OCR text directly
        logger.info(f"[{image_id}] No bottles detected, trying direct OCR match")
        return await _direct_ocr_response(
            image_id, vision_result, wine_matcher, use_llm, debug_mode
        )

    # Step 2: Group text to bottles and normalize (also track orphaned text)
    ocr_processor = OCRProcessor()
    ocr_result = ocr_processor.process_with_orphans(
        vision_result.objects,
        vision_result.text_blocks,
        debug=debug_mode,
    )
    bottle_texts = ocr_result.bottle_texts
    orphaned_texts = ocr_result.orphaned_texts

    # Track bottles with/without text
    stats_bottles_with_text = sum(1 for bt in bottle_texts if bt.combined_text)
    stats_bottles_empty = len(bottle_texts) - stats_bottles_with_text
    logger.info(f"[{image_id}] TEXT ASSIGNMENT: {stats_bottles_with_text} with text, {stats_bottles_empty} empty")

    if orphaned_texts:
        logger.info(f"[{image_id}] {len(orphaned_texts)} orphaned text blocks not assigned to bottles")

    # Step 3 & 4: Tiered recognition (fuzzy match → LLM fallback)
    # Always enable debug mode to collect pipeline stats
    pipeline = get_pipeline(use_llm=use_llm, debug_mode=True)
    recognized = await pipeline.recognize(bottle_texts)

    # Count matches by source
    from ..models.enums import WineSource
    stats_fuzzy_matched = sum(1 for w in recognized if w.source == WineSource.DATABASE)
    stats_llm_validated = sum(1 for w in recognized if w.source == WineSource.LLM)

    logger.info(f"[{image_id}] MATCHED: {len(recognized)} of {len(bottle_texts)} bottles (fuzzy={stats_fuzzy_matched}, llm={stats_llm_validated})")
    if Config.debug_mode():
        for w in recognized:
            logger.debug(f"[{image_id}]   {w.wine_name}: rating={w.rating}, conf={w.confidence:.2f}, src={w.source}")

    # Step 5: Claude Vision fallback for unmatched OR low-confidence bottles
    # Send to Vision if:
    # - Bottle wasn't matched by the pipeline, OR
    # - Bottle was matched but confidence < TAPPABLE_THRESHOLD (would be non-clickable)
    # This ensures all displayed bottles are tappable with good identification

    # Build map of bottle_id -> recognized wine for low-confidence check
    bottle_to_wine = {id(w.bottle_text): w for w in recognized}

    bottles_for_vision: list[BottleText] = []
    low_conf_bottle_ids: set[int] = set()  # Track which were low-confidence (for replacement)

    for bt in bottle_texts:
        bt_id = id(bt)
        if bt_id not in bottle_to_wine:
            # Unmatched - send to Vision
            bottles_for_vision.append(bt)
        elif bottle_to_wine[bt_id].confidence < Config.TAPPABLE_THRESHOLD:
            # Low confidence (non-tappable) - send to Vision for better identification
            bottles_for_vision.append(bt)
            low_conf_bottle_ids.add(bt_id)
            logger.info(
                f"[{image_id}] Low-confidence match sent to Vision: "
                f"{bottle_to_wine[bt_id].wine_name} (conf={bottle_to_wine[bt_id].confidence:.2f})"
            )
        elif bottle_to_wine[bt_id].rating is None:
            # Identified but no rating - send to Vision for rating estimation
            bottles_for_vision.append(bt)
            low_conf_bottle_ids.add(bt_id)
            logger.info(
                f"[{image_id}] No-rating match sent to Vision: "
                f"{bottle_to_wine[bt_id].wine_name} (conf={bottle_to_wine[bt_id].confidence:.2f})"
            )

    # Use vision fallback if enabled both via parameter and config
    stats_unmatched_count = len(bottles_for_vision)
    enable_vision = use_vision_fallback and Config.use_vision_fallback()
    logger.info(f"[{image_id}] BOTTLES FOR VISION: {stats_unmatched_count} (unmatched or low-confidence)")

    if bottles_for_vision and enable_vision:
        stats_vision_attempted = len(bottles_for_vision)
        try:
            vision_service = get_claude_vision_service()
            vision_results = await vision_service.identify_wines(
                image_bytes=image_bytes,
                unmatched_bottles=bottles_for_vision,
                image_media_type="image/jpeg",  # We convert to JPEG earlier
            )

            # Convert vision results to RecognizedWine
            for vision_wine in vision_results:
                if vision_wine.wine_name and vision_wine.bottle_index < len(bottles_for_vision):
                    bottle_text = bottles_for_vision[vision_wine.bottle_index]
                    bt_id = id(bottle_text)
                    recognized_wine = _vision_to_recognized(vision_wine, bottle_text)

                    if bt_id in low_conf_bottle_ids:
                        # Check if we'd downgrade a real DB rating to a default rating
                        existing_wine = bottle_to_wine.get(bt_id)
                        has_real_db_rating = (
                            existing_wine is not None
                            and existing_wine.rating is not None
                            and existing_wine.rating_source == RatingSource.DATABASE
                        )
                        vision_has_real_rating = vision_wine.estimated_rating is not None

                        if has_real_db_rating and not vision_has_real_rating:
                            # Keep the DB-rated wine — don't downgrade to default 3.5
                            logger.info(
                                f"[{image_id}] Vision SKIPPED replacement (would downgrade "
                                f"DB rating {existing_wine.rating} to default): "
                                f"{vision_wine.wine_name} (conf={vision_wine.confidence:.2f})"
                            )
                        else:
                            # Replace the low-confidence match with Vision result
                            recognized = [w for w in recognized if id(w.bottle_text) != bt_id]
                            recognized.append(recognized_wine)
                            logger.info(
                                f"[{image_id}] Vision REPLACED low-conf match: {vision_wine.wine_name} "
                                f"(conf={vision_wine.confidence:.2f}, rating={vision_wine.estimated_rating})"
                            )
                    else:
                        # Add new result for previously unmatched bottle
                        recognized.append(recognized_wine)
                        logger.info(
                            f"[{image_id}] Vision identified: {vision_wine.wine_name} "
                            f"(conf={vision_wine.confidence:.2f}, rating={vision_wine.estimated_rating})"
                        )
                    stats_vision_identified += 1

            # Cache Vision-identified wines for future lookups
            llm_cache = get_llm_rating_cache()
            for vision_wine in vision_results:
                if vision_wine.wine_name and vision_wine.estimated_rating is not None and vision_wine.bottle_index < len(bottles_for_vision):
                    # Skip caching garbage names (too long or too many words)
                    if len(vision_wine.wine_name) > 80 or len(vision_wine.wine_name.split()) > 10:
                        continue
                    capped_conf = min(vision_wine.confidence, Config.VISION_FALLBACK_CONFIDENCE_CAP)
                    cache_kwargs = dict(
                        estimated_rating=vision_wine.estimated_rating,
                        confidence=capped_conf,
                        llm_provider="claude_vision",
                        wine_type=vision_wine.wine_type,
                        region=vision_wine.region,
                        varietal=vision_wine.varietal,
                        brand=vision_wine.brand,
                    )
                    # Cache under the canonical wine name
                    llm_cache.set(wine_name=vision_wine.wine_name, **cache_kwargs)
                    # Also cache under the normalized OCR text so the pipeline
                    # can find it on future scans without re-calling Vision
                    bt = bottles_for_vision[vision_wine.bottle_index]
                    if bt.normalized_name and len(bt.normalized_name) <= 80 and bt.normalized_name.lower() != vision_wine.wine_name.lower():
                        llm_cache.set(wine_name=bt.normalized_name, **cache_kwargs)
                    logger.debug(f"[{image_id}] Cached Vision result: {vision_wine.wine_name} (rating={vision_wine.estimated_rating})")

            logger.info(f"[{image_id}] VISION RESULTS: {stats_vision_identified} of {stats_vision_attempted} identified")
        except Exception as e:
            stats_vision_error = str(e)
            logger.warning(f"[{image_id}] Claude Vision fallback failed: {e}")

    # Step 6: LLM batch rescue for remaining unmatched bottles and orphaned text
    # This is the final catch-all: sends ALL remaining raw OCR text to the LLM
    # in a single batch for cross-referenced identification. Unlike earlier steps
    # which process each bottle independently, this gives the LLM the full context
    # of remaining shelf text, letting it piece together fragmented OCR.
    stats_llm_rescue_attempted = 0
    stats_llm_rescue_identified = 0
    rescued_orphan_fallback: list[FallbackWine] = []

    recognized_bt_ids = {id(w.bottle_text) for w in recognized}
    rescue_bottles: list[BottleText] = []
    for bt in bottle_texts:
        if id(bt) not in recognized_bt_ids:
            raw_text = bt.combined_text or ""
            if len(raw_text.strip()) >= 5:
                rescue_bottles.append(bt)

    # Also collect orphaned texts not yet matched
    rescue_orphans: list[OrphanedText] = []
    existing_wine_names = {w.wine_name.lower() for w in recognized}
    for orphan in orphaned_texts:
        raw_text = orphan.text or ""
        if len(raw_text.strip()) >= 5:
            rescue_orphans.append(orphan)

    if (rescue_bottles or rescue_orphans) and use_llm:
        stats_llm_rescue_attempted = len(rescue_bottles) + len(rescue_orphans)
        logger.info(
            f"[{image_id}] LLM RESCUE: Attempting batch rescue for "
            f"{len(rescue_bottles)} unmatched bottles + {len(rescue_orphans)} orphaned texts"
        )

        try:
            normalizer = get_normalizer(use_mock=False)
            rescue_items: list[BatchValidationItem] = []
            # Track source: ('bottle', BottleText) or ('orphan', OrphanedText)
            rescue_sources: list[tuple[str, object]] = []

            for bt in rescue_bottles:
                rescue_items.append(BatchValidationItem(
                    ocr_text=bt.combined_text,
                    db_candidate=None,
                    db_rating=None,
                ))
                rescue_sources.append(('bottle', bt))

            for orphan in rescue_orphans:
                rescue_items.append(BatchValidationItem(
                    ocr_text=orphan.text,  # Use raw text, not normalized
                    db_candidate=None,
                    db_rating=None,
                ))
                rescue_sources.append(('orphan', orphan))

            rescue_results = await normalizer.validate_batch(rescue_items)

            for (source_type, source), validation in zip(rescue_sources, rescue_results):
                if not validation.wine_name or validation.confidence < 0.5:
                    continue
                if _is_llm_generic_response(validation.wine_name):
                    continue

                # Deduplicate against existing results
                name_lower = validation.wine_name.lower()
                if name_lower in existing_wine_names:
                    continue

                # Try to match LLM-identified wine against DB for a better rating
                rating = validation.estimated_rating
                rating_source = RatingSource.LLM_ESTIMATED if rating is not None else RatingSource.NONE
                wine_name = validation.wine_name
                wine_id = None

                db_match = wine_matcher.match(validation.wine_name)
                if db_match and db_match.confidence >= 0.90:
                    wine_name = db_match.canonical_name
                    if db_match.rating is not None:
                        rating = db_match.rating
                        rating_source = RatingSource.DATABASE
                    wine_id = db_match.wine_id

                if source_type == 'bottle':
                    bt = source
                    # Cap confidence: ensure tappable but not top-3 emphasis
                    capped_conf = max(
                        Config.VISION_CONFIDENCE_FLOOR,
                        min(validation.confidence, Config.VISION_FALLBACK_CONFIDENCE_CAP)
                    )

                    result = RecognizedWine(
                        wine_name=wine_name,
                        rating=rating if rating is not None else Config.VISION_DEFAULT_RATING,
                        confidence=capped_conf,
                        source=WineSource.LLM,
                        identified=True,
                        bottle_text=bt,
                        rating_source=rating_source if rating is not None else RatingSource.DEFAULT,
                        wine_type=validation.wine_type,
                        brand=validation.brand,
                        region=validation.region,
                        varietal=validation.varietal,
                        wine_id=wine_id,
                    )
                    recognized.append(result)
                    existing_wine_names.add(wine_name.lower())
                    stats_llm_rescue_identified += 1
                    logger.info(
                        f"[{image_id}] LLM RESCUE identified bottle: {wine_name} "
                        f"(conf={capped_conf:.2f}, rating={result.rating})"
                    )

                elif source_type == 'orphan':
                    # Orphans have no bounding box — add to fallback list
                    if rating is not None:
                        rescued_orphan_fallback.append(FallbackWine(
                            wine_name=wine_name,
                            rating=rating,
                        ))
                        existing_wine_names.add(wine_name.lower())
                        stats_llm_rescue_identified += 1
                        logger.info(
                            f"[{image_id}] LLM RESCUE identified orphan: {wine_name} "
                            f"(rating={rating})"
                        )

            logger.info(
                f"[{image_id}] LLM RESCUE RESULTS: {stats_llm_rescue_identified} "
                f"of {stats_llm_rescue_attempted} identified"
            )
        except Exception as e:
            logger.warning(f"[{image_id}] LLM batch rescue failed: {e}")

    # Enrich recognized wines with actual review data from wine_reviews table
    _enrich_with_reviews(recognized, wine_matcher)

    # Deduplicate recognized wines by name (keep highest confidence)
    seen_wines = {}
    for wine in recognized:
        name_key = wine.wine_name.lower().strip()
        if name_key not in seen_wines or wine.confidence > seen_wines[name_key].confidence:
            seen_wines[name_key] = wine
    recognized = list(seen_wines.values())

    # Build response
    results: list[WineResult] = []
    fallback: list[FallbackWine] = []

    for wine in recognized:
        if wine.confidence >= Config.VISIBILITY_THRESHOLD:
            # Add to positioned results
            results.append(_to_wine_result(wine))
        elif wine.rating is not None:
            # Low confidence with rating → fallback
            fallback.append(FallbackWine(
                wine_name=wine.wine_name,
                rating=wine.rating
            ))

    # Step 7: Process orphaned text blocks into fallback list
    # These are OCR texts not near any detected bottle - may be from undetected bottles
    if orphaned_texts:
        orphan_matches = _process_orphaned_texts(orphaned_texts, wine_matcher)
        if orphan_matches:
            logger.info(f"[{image_id}] Matched {len(orphan_matches)} wines from orphaned text")
            # Add to fallback, avoiding duplicates
            existing_names = {f.wine_name.lower() for f in fallback}
            existing_names.update(r.wine_name.lower() for r in results)
            for match in orphan_matches:
                if match.wine_name.lower() not in existing_names:
                    fallback.append(match)
                    existing_names.add(match.wine_name.lower())

    # Step 8: Add LLM-rescued orphan wines to fallback list
    if rescued_orphan_fallback:
        existing_names = {f.wine_name.lower() for f in fallback}
        existing_names.update(r.wine_name.lower() for r in results)
        for rescued in rescued_orphan_fallback:
            if rescued.wine_name.lower() not in existing_names:
                fallback.append(rescued)
                existing_names.add(rescued.wine_name.lower())

    # Sort results by rating (wines with ratings first, then by rating value)
    results.sort(key=lambda x: (x.rating is not None, x.rating or 0), reverse=True)
    fallback.sort(key=lambda x: x.rating, reverse=True)

    # === Feature-flagged post-processing ===
    if flags:
        _apply_feature_flags(results, flags, wine_matcher=wine_matcher)

    stats_final_results = len(results)
    logger.info(f"[{image_id}] Response: {stats_final_results} results, {len(fallback)} fallback")

    # Log pipeline summary
    logger.info(
        f"[{image_id}] === PIPELINE SUMMARY ===\n"
        f"  Bottles detected by Vision API: {stats_bottles_detected}\n"
        f"  Bottles with OCR text: {stats_bottles_with_text} ({stats_bottles_empty} empty)\n"
        f"  Fuzzy matches (high conf): {stats_fuzzy_matched}\n"
        f"  LLM validated/identified: {stats_llm_validated}\n"
        f"  Sent to Vision (unmatched/low-conf): {stats_unmatched_count}\n"
        f"  Claude Vision attempted: {stats_vision_attempted}\n"
        f"  Claude Vision identified: {stats_vision_identified}"
        + (f" (ERROR: {stats_vision_error})" if stats_vision_error else "") +
        f"\n  LLM rescue attempted: {stats_llm_rescue_attempted}\n"
        f"  LLM rescue identified: {stats_llm_rescue_identified}\n"
        f"  Final results: {stats_final_results}"
    )

    # Build pipeline stats
    pipeline_stats = PipelineStats(
        bottles_detected=stats_bottles_detected,
        bottles_with_text=stats_bottles_with_text,
        bottles_empty=stats_bottles_empty,
        fuzzy_matched=stats_fuzzy_matched,
        llm_validated=stats_llm_validated,
        unmatched_count=stats_unmatched_count,
        vision_attempted=stats_vision_attempted,
        vision_identified=stats_vision_identified,
        vision_error=stats_vision_error,
        llm_rescue_attempted=stats_llm_rescue_attempted,
        llm_rescue_identified=stats_llm_rescue_identified,
        final_results=stats_final_results
    )

    # Always build debug data (pipeline_stats is always useful)
    debug_data = DebugData(
        pipeline_steps=pipeline.debug_steps,
        total_ocr_texts=len(bottle_texts),
        bottles_detected=stats_bottles_detected,
        texts_matched=len([s for s in pipeline.debug_steps if s.included_in_results]),
        llm_calls_made=pipeline.llm_call_count,
        pipeline_stats=pipeline_stats
    )

    # Auto-sync LLM/Vision-discovered wines back to the database
    sync_discovered_wines(results, fallback)

    return ScanResponse(
        image_id=image_id,
        results=results,
        fallback_list=fallback,
        debug=debug_data
    )


async def _direct_ocr_response(
    image_id: str,
    vision_result: VisionResult,
    wine_matcher: WineMatcher,
    use_llm: bool,
    debug_mode: bool
) -> ScanResponse:
    """
    Handle case where no bottles detected but OCR text exists.

    Creates a synthetic bottle from all the text and tries to match it.
    This handles close-up label shots where bottle shape isn't visible.
    """
    from ..services.ocr_processor import BottleText
    from ..services.vision import DetectedObject, BoundingBox as VisionBBox

    # Combine all text blocks
    all_text = ' '.join([tb.text for tb in vision_result.text_blocks])
    logger.info(f"[{image_id}] Direct OCR text: {all_text[:100]}...")

    if not all_text or len(all_text.strip()) < 3:
        return _fallback_response(image_id, wine_matcher)

    # Create a synthetic bottle covering the whole image
    synthetic_bottle = DetectedObject(
        name="Bottle",
        confidence=0.9,  # Slightly lower since we didn't detect it
        bbox=VisionBBox(x=0.0, y=0.0, width=1.0, height=1.0)
    )

    # Process OCR
    ocr_processor = OCRProcessor()
    normalized_text = ocr_processor._normalize_text(all_text)

    if not normalized_text or len(normalized_text.strip()) < 3:
        return _fallback_response(image_id, wine_matcher)

    # Create bottle text
    bottle_text = BottleText(
        bottle=synthetic_bottle,
        text_fragments=[all_text],
        combined_text=all_text,
        normalized_name=normalized_text
    )

    # Run pipeline (always enable debug for stats collection)
    pipeline = get_pipeline(use_llm=use_llm, debug_mode=True)
    recognized = await pipeline.recognize([bottle_text])

    logger.info(f"[{image_id}] Direct OCR recognized {len(recognized)} wines")

    results: list[WineResult] = []
    fallback: list[FallbackWine] = []

    for wine in recognized:
        if wine.confidence >= Config.VISIBILITY_THRESHOLD:
            results.append(_to_wine_result(wine))
        elif wine.rating is not None:
            fallback.append(FallbackWine(
                wine_name=wine.wine_name,
                rating=wine.rating
            ))

    # If no results, add to fallback
    if not results and not fallback:
        return _fallback_response(image_id, wine_matcher)

    # Build debug data if requested
    debug_data = None
    if debug_mode:
        debug_data = DebugData(
            pipeline_steps=pipeline.debug_steps,
            total_ocr_texts=1,
            bottles_detected=0,
            texts_matched=len([s for s in pipeline.debug_steps if s.included_in_results]),
            llm_calls_made=pipeline.llm_call_count
        )

    # Auto-sync LLM/Vision-discovered wines back to the database
    sync_discovered_wines(results, fallback)

    return ScanResponse(
        image_id=image_id,
        results=results,
        fallback_list=fallback,
        debug=debug_data if debug_mode else None
    )


def _fallback_response(image_id: str, wine_matcher: WineMatcher) -> ScanResponse:
    """Return empty results with common wines in fallback."""
    # Add some popular wines to fallback
    popular_wines = [
        "Caymus Cabernet Sauvignon",
        "Opus One",
        "La Crema Sonoma Coast Pinot Noir",
        "Kendall-Jackson Vintner's Reserve Chardonnay",
    ]

    fallback = []
    for name in popular_wines:
        match = wine_matcher.match(name)
        if match and match.rating is not None:
            fallback.append(FallbackWine(
                wine_name=match.canonical_name,
                rating=match.rating
            ))

    return ScanResponse(
        image_id=image_id,
        results=[],
        fallback_list=fallback
    )


@router.post("/scan/debug")
async def scan_debug(
    image: UploadFile = File(..., description="Wine shelf image"),
) -> dict:
    """
    Debug endpoint: raw OCR results + wine name extraction.

    Returns raw OCR text from Vision API and extracted wine names.
    Use this to test OCR quality before full pipeline processing.
    """
    # Validate content type
    if image.content_type not in Config.ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid image type. Only JPEG and PNG are supported."
        )

    try:
        image_bytes = await image.read()
    except IOError as e:
        logger.error(f"Failed to read uploaded image for debug: {e}")
        raise HTTPException(status_code=400, detail="Failed to read image file")

    # Convert HEIC/HEIF to JPEG
    image_bytes = convert_heic_to_jpeg(image_bytes, image.content_type)

    # Validate file size
    if len(image_bytes) > Config.MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Maximum size is {Config.MAX_IMAGE_SIZE_MB}MB."
        )

    try:
        vision_service = VisionService()
        result = vision_service.analyze(image_bytes)

        # Extract wine names from raw OCR text
        wine_names = extract_wine_names(result.raw_text)

        return {
            "labels_identified": len(wine_names),
            "wine_names": wine_names,
            "raw_ocr_text": result.raw_text,
            "bottles_detected": len(result.objects),
        }
    except ValueError as e:
        logger.warning(f"Invalid image in debug endpoint: {e}")
        raise HTTPException(status_code=400, detail="Invalid image format")
    except Exception as e:
        logger.error(f"Debug endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@router.post("/preview")
async def preview_image(
    image: UploadFile = File(..., description="Image to convert for preview"),
) -> Response:
    """
    Convert an image to JPEG for preview display.

    Useful for HEIC files that browsers can't display natively.
    Returns the image as JPEG bytes with appropriate content type.
    """
    # Validate content type
    if image.content_type not in Config.ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid image type."
        )

    try:
        image_bytes = await image.read()
    except IOError as e:
        logger.error(f"Failed to read uploaded image for preview: {e}")
        raise HTTPException(status_code=400, detail="Failed to read image file")

    # Validate file size
    if len(image_bytes) > Config.MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Maximum size is {Config.MAX_IMAGE_SIZE_MB}MB."
        )

    try:
        # Convert to JPEG (handles HEIC/HEIF, passes through JPEG/PNG)
        img = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if needed
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Save as JPEG
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=85)
        jpeg_bytes = output.getvalue()

        return Response(
            content=jpeg_bytes,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-cache"}
        )
    except Exception as e:
        logger.error(f"Failed to convert image for preview: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Failed to process image")


@router.get("/cache/stats")
async def cache_stats():
    """
    Get cache statistics for monitoring.

    Returns stats for:
    - Vision API response cache (if enabled)
    - LLM rating cache
    """
    from ..services.vision_cache import get_vision_cache
    from ..services.llm_rating_cache import get_llm_rating_cache

    return {
        "vision_cache": get_vision_cache().get_stats(),
        "llm_rating_cache": get_llm_rating_cache().get_stats(),
    }
