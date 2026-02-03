"""
Image cropping utilities for wine bottle extraction.

Crops bottle regions from shelf images for individual analysis.
Used by Claude Vision fallback to focus on specific bottles.
"""

import io
import logging
from dataclasses import dataclass
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class CropResult:
    """Result of cropping a bottle region."""
    image_bytes: bytes
    original_width: int
    original_height: int
    crop_x: int
    crop_y: int
    crop_width: int
    crop_height: int


@dataclass
class NormalizedBBox:
    """Bounding box with normalized coordinates (0-1)."""
    x: float
    y: float
    width: float
    height: float


def crop_bottle_region(
    image_bytes: bytes,
    bbox: NormalizedBBox,
    padding: float = 0.05,
    max_dimension: int = 800,
    jpeg_quality: int = 85,
) -> Optional[CropResult]:
    """
    Extract a bottle region from an image.

    Args:
        image_bytes: The full shelf image as bytes
        bbox: Normalized bounding box (0-1 coordinates)
        padding: Extra padding around the bbox (0.05 = 5%)
        max_dimension: Resize if larger than this (preserves aspect ratio)
        jpeg_quality: JPEG compression quality (0-100)

    Returns:
        CropResult with cropped image bytes, or None if cropping fails
    """
    try:
        # Open image
        img = Image.open(io.BytesIO(image_bytes))
        original_width, original_height = img.size

        # Convert normalized coords to pixels
        x = int(bbox.x * original_width)
        y = int(bbox.y * original_height)
        w = int(bbox.width * original_width)
        h = int(bbox.height * original_height)

        # Add padding (clamped to image bounds)
        pad_x = int(w * padding)
        pad_y = int(h * padding)

        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = min(original_width, x + w + pad_x)
        y2 = min(original_height, y + h + pad_y)

        # Crop the region
        cropped = img.crop((x1, y1, x2, y2))
        crop_width, crop_height = cropped.size

        # Resize if too large
        if max(crop_width, crop_height) > max_dimension:
            ratio = max_dimension / max(crop_width, crop_height)
            new_width = int(crop_width * ratio)
            new_height = int(crop_height * ratio)
            cropped = cropped.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Convert to RGB if needed (for JPEG)
        if cropped.mode in ("RGBA", "P"):
            cropped = cropped.convert("RGB")

        # Save as JPEG
        output = io.BytesIO()
        cropped.save(output, format="JPEG", quality=jpeg_quality)

        return CropResult(
            image_bytes=output.getvalue(),
            original_width=original_width,
            original_height=original_height,
            crop_x=x1,
            crop_y=y1,
            crop_width=crop_width,
            crop_height=crop_height,
        )

    except Exception as e:
        logger.error(f"Failed to crop bottle region: {e}")
        return None


def crop_multiple_bottles(
    image_bytes: bytes,
    bboxes: list[NormalizedBBox],
    padding: float = 0.05,
    max_dimension: int = 800,
    jpeg_quality: int = 85,
) -> list[Optional[CropResult]]:
    """
    Crop multiple bottle regions from an image.

    More efficient than calling crop_bottle_region multiple times
    since the image is only opened once.

    Args:
        image_bytes: The full shelf image as bytes
        bboxes: List of normalized bounding boxes
        padding: Extra padding around each bbox
        max_dimension: Max size for resizing
        jpeg_quality: JPEG compression quality

    Returns:
        List of CropResult (or None for failed crops), same order as input
    """
    results: list[Optional[CropResult]] = []

    try:
        img = Image.open(io.BytesIO(image_bytes))
        original_width, original_height = img.size

        for bbox in bboxes:
            try:
                # Convert normalized coords to pixels
                x = int(bbox.x * original_width)
                y = int(bbox.y * original_height)
                w = int(bbox.width * original_width)
                h = int(bbox.height * original_height)

                # Add padding
                pad_x = int(w * padding)
                pad_y = int(h * padding)

                x1 = max(0, x - pad_x)
                y1 = max(0, y - pad_y)
                x2 = min(original_width, x + w + pad_x)
                y2 = min(original_height, y + h + pad_y)

                # Crop
                cropped = img.crop((x1, y1, x2, y2))
                crop_width, crop_height = cropped.size

                # Resize if needed
                if max(crop_width, crop_height) > max_dimension:
                    ratio = max_dimension / max(crop_width, crop_height)
                    new_width = int(crop_width * ratio)
                    new_height = int(crop_height * ratio)
                    cropped = cropped.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Convert to RGB
                if cropped.mode in ("RGBA", "P"):
                    cropped = cropped.convert("RGB")

                # Save as JPEG
                output = io.BytesIO()
                cropped.save(output, format="JPEG", quality=jpeg_quality)

                results.append(CropResult(
                    image_bytes=output.getvalue(),
                    original_width=original_width,
                    original_height=original_height,
                    crop_x=x1,
                    crop_y=y1,
                    crop_width=crop_width,
                    crop_height=crop_height,
                ))

            except Exception as e:
                logger.warning(f"Failed to crop bottle: {e}")
                results.append(None)

    except Exception as e:
        logger.error(f"Failed to open image for batch cropping: {e}")
        return [None] * len(bboxes)

    return results
