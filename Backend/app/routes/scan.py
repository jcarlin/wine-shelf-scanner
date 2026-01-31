"""
/scan endpoint for Wine Shelf Scanner.

Receives an image and returns wine detection results.
"""

import os
import uuid
from typing import Optional
from fastapi import APIRouter, File, UploadFile, HTTPException

from ..models import ScanResponse
from ..mocks.fixtures import get_mock_response

router = APIRouter()


@router.post("/scan", response_model=ScanResponse)
async def scan_shelf(
    image: UploadFile = File(..., description="Wine shelf image"),
    mock_scenario: Optional[str] = None,
) -> ScanResponse:
    """
    Scan a wine shelf image and return detected wines with ratings.

    Args:
        image: The shelf image (JPEG or PNG)
        mock_scenario: Optional fixture name for testing (full_shelf, partial_detection, etc.)

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

    if use_mocks or mock_scenario:
        scenario = mock_scenario or "full_shelf"
        return get_mock_response(image_id, scenario)

    # TODO: Phase 2 - Implement actual Vision API processing
    # For now, return mock response
    return get_mock_response(image_id, "full_shelf")


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
