"""
/scan endpoint for Wine Shelf Scanner.

Receives an image and returns wine detection results.
"""

import os
import uuid
from typing import Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, Query

from ..models import ScanResponse, WineResult, FallbackWine, BoundingBox
from ..mocks.fixtures import get_mock_response
from ..services.vision import VisionService, MockVisionService
from ..services.ocr_processor import OCRProcessor, extract_wine_names
from ..services.wine_matcher import WineMatcher

router = APIRouter()

# Initialize services (singleton pattern)
_wine_matcher: Optional[WineMatcher] = None


def get_wine_matcher() -> WineMatcher:
    """Get or create wine matcher instance."""
    global _wine_matcher
    if _wine_matcher is None:
        _wine_matcher = WineMatcher()
    return _wine_matcher


@router.post("/scan", response_model=ScanResponse)
async def scan_shelf(
    image: UploadFile = File(..., description="Wine shelf image"),
    mock_scenario: Optional[str] = Query(None, description="Mock scenario for testing"),
    use_vision_api: bool = Query(False, description="Use real Vision API"),
) -> ScanResponse:
    """
    Scan a wine shelf image and return detected wines with ratings.

    Args:
        image: The shelf image (JPEG or PNG)
        mock_scenario: Optional fixture name for testing (full_shelf, partial_detection, etc.)
        use_vision_api: Whether to use real Google Vision API (requires credentials)

    Returns:
        ScanResponse with detected wines and fallback list
    """
    # Validate image type
    if image.content_type not in ["image/jpeg", "image/png"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid image type. Only JPEG and PNG are supported."
        )

    # Generate unique image ID
    image_id = str(uuid.uuid4())

    # Check if we should use mocks
    use_mocks = os.getenv("USE_MOCKS", "true").lower() == "true"

    if mock_scenario:
        # Explicit mock scenario requested
        return get_mock_response(image_id, mock_scenario)

    if use_mocks and not use_vision_api:
        # Default to mock response
        return get_mock_response(image_id, "full_shelf")

    # Real processing pipeline
    try:
        image_bytes = await image.read()
        return await process_image(image_id, image_bytes, use_vision_api)
    except Exception as e:
        # Log error and return fallback
        print(f"Error processing image: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing image: {str(e)}"
        )


async def process_image(
    image_id: str,
    image_bytes: bytes,
    use_real_api: bool = False
) -> ScanResponse:
    """
    Full processing pipeline:
    1. Vision API (object detection + OCR)
    2. OCR grouping (text → bottle assignment)
    3. Text normalization
    4. Wine matching (fuzzy lookup in ratings DB)
    5. Response construction
    """
    # Choose vision service
    if use_real_api:
        vision_service = VisionService()
    else:
        vision_service = MockVisionService("full_shelf")

    # Step 1: Analyze image
    vision_result = vision_service.analyze(image_bytes)

    if not vision_result.objects:
        # No bottles detected - return fallback only
        return _fallback_response(image_id)

    # Step 2 & 3: Group text to bottles and normalize
    ocr_processor = OCRProcessor()
    bottle_texts = ocr_processor.process(
        vision_result.objects,
        vision_result.text_blocks
    )

    # Step 4: Match against ratings database
    wine_matcher = get_wine_matcher()
    results: list[WineResult] = []
    fallback: list[FallbackWine] = []

    for bt in bottle_texts:
        match = wine_matcher.match(bt.normalized_name)

        if match and match.confidence >= 0.6:
            # Good match - add to results with position
            results.append(WineResult(
                wine_name=match.canonical_name,
                rating=match.rating,
                confidence=min(bt.bottle.confidence, match.confidence),
                bbox=BoundingBox(
                    x=bt.bottle.bbox.x,
                    y=bt.bottle.bbox.y,
                    width=bt.bottle.bbox.width,
                    height=bt.bottle.bbox.height
                )
            ))
        elif match:
            # Low confidence match - add to fallback
            fallback.append(FallbackWine(
                wine_name=match.canonical_name,
                rating=match.rating
            ))
        elif bt.normalized_name:
            # No match but we have text - add unknown to fallback
            fallback.append(FallbackWine(
                wine_name=bt.normalized_name,
                rating=3.0  # Default rating for unknown wines
            ))

    # Sort results by rating (highest first)
    results.sort(key=lambda x: x.rating, reverse=True)
    fallback.sort(key=lambda x: x.rating, reverse=True)

    return ScanResponse(
        image_id=image_id,
        results=results,
        fallback_list=fallback
    )


def _fallback_response(image_id: str) -> ScanResponse:
    """Return empty results with common wines in fallback."""
    wine_matcher = get_wine_matcher()

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
        if match:
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
    # Validate image type
    if image.content_type not in ["image/jpeg", "image/png"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid image type. Only JPEG and PNG are supported."
        )

    try:
        image_bytes = await image.read()
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
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing image: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
