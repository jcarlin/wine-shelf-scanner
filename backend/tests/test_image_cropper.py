"""
Tests for the image cropper utility.
"""

import io
import pytest
from PIL import Image

from app.services.image_cropper import (
    crop_bottle_region,
    crop_multiple_bottles,
    CropResult,
    NormalizedBBox,
)


def create_test_image(width: int = 1000, height: int = 800) -> bytes:
    """Create a test image with gradient for testing crop positioning."""
    img = Image.new("RGB", (width, height))
    # Fill with a gradient so we can verify crop positions
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            r = int(255 * x / width)
            g = int(255 * y / height)
            b = 128
            pixels[x, y] = (r, g, b)

    output = io.BytesIO()
    img.save(output, format="JPEG", quality=90)
    return output.getvalue()


class TestCropBottleRegion:
    """Tests for crop_bottle_region function."""

    def test_crops_center_region(self):
        """Test cropping a region from the center of the image."""
        image_bytes = create_test_image(1000, 800)
        bbox = NormalizedBBox(x=0.4, y=0.3, width=0.2, height=0.4)

        result = crop_bottle_region(image_bytes, bbox, padding=0)

        assert result is not None
        assert isinstance(result, CropResult)
        assert result.original_width == 1000
        assert result.original_height == 800
        assert result.crop_x == 400  # 0.4 * 1000
        assert result.crop_y == 240  # 0.3 * 800
        assert result.crop_width == 200  # 0.2 * 1000
        assert result.crop_height == 320  # 0.4 * 800

    def test_applies_padding(self):
        """Test that padding expands the crop region."""
        image_bytes = create_test_image(1000, 800)
        bbox = NormalizedBBox(x=0.3, y=0.3, width=0.2, height=0.2)

        # Without padding
        no_padding = crop_bottle_region(image_bytes, bbox, padding=0)
        # With 10% padding
        with_padding = crop_bottle_region(image_bytes, bbox, padding=0.1)

        assert no_padding is not None
        assert with_padding is not None

        # With padding should have larger dimensions
        crop_no_pad = Image.open(io.BytesIO(no_padding.image_bytes))
        crop_with_pad = Image.open(io.BytesIO(with_padding.image_bytes))

        # The padded version should be wider and taller
        assert crop_with_pad.width >= crop_no_pad.width
        assert crop_with_pad.height >= crop_no_pad.height

    def test_padding_clamps_to_bounds(self):
        """Test that padding doesn't exceed image bounds."""
        image_bytes = create_test_image(1000, 800)
        # Bbox at top-left corner
        bbox = NormalizedBBox(x=0.0, y=0.0, width=0.1, height=0.1)

        result = crop_bottle_region(image_bytes, bbox, padding=0.5)

        assert result is not None
        # Should clamp to 0, not go negative
        assert result.crop_x == 0
        assert result.crop_y == 0

    def test_respects_max_dimension(self):
        """Test that result is resized if larger than max_dimension."""
        image_bytes = create_test_image(2000, 1600)
        bbox = NormalizedBBox(x=0.0, y=0.0, width=1.0, height=1.0)

        result = crop_bottle_region(image_bytes, bbox, max_dimension=500)

        assert result is not None
        cropped = Image.open(io.BytesIO(result.image_bytes))
        assert max(cropped.width, cropped.height) <= 500

    def test_converts_rgba_to_rgb(self):
        """Test that RGBA images are converted to RGB for JPEG output."""
        # Create RGBA image
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        output = io.BytesIO()
        img.save(output, format="PNG")
        image_bytes = output.getvalue()

        bbox = NormalizedBBox(x=0.0, y=0.0, width=1.0, height=1.0)
        result = crop_bottle_region(image_bytes, bbox)

        assert result is not None
        # Should be valid JPEG
        cropped = Image.open(io.BytesIO(result.image_bytes))
        assert cropped.format == "JPEG"
        assert cropped.mode == "RGB"

    def test_returns_none_on_invalid_image(self):
        """Test that invalid image bytes return None."""
        result = crop_bottle_region(b"not an image", NormalizedBBox(0, 0, 1, 1))
        assert result is None


class TestCropMultipleBottles:
    """Tests for crop_multiple_bottles function."""

    def test_crops_multiple_regions(self):
        """Test cropping multiple regions from one image."""
        image_bytes = create_test_image(1000, 800)
        bboxes = [
            NormalizedBBox(x=0.1, y=0.1, width=0.2, height=0.3),
            NormalizedBBox(x=0.4, y=0.2, width=0.2, height=0.3),
            NormalizedBBox(x=0.7, y=0.1, width=0.2, height=0.3),
        ]

        results = crop_multiple_bottles(image_bytes, bboxes, padding=0)

        assert len(results) == 3
        assert all(r is not None for r in results)
        # All should have same original dimensions
        assert all(r.original_width == 1000 for r in results)
        assert all(r.original_height == 800 for r in results)

    def test_handles_empty_list(self):
        """Test with empty bbox list."""
        image_bytes = create_test_image()
        results = crop_multiple_bottles(image_bytes, [])
        assert results == []

    def test_handles_partial_failures(self):
        """Test that one bad bbox doesn't fail all crops."""
        image_bytes = create_test_image(1000, 800)
        # Note: Our implementation doesn't actually fail on out-of-bounds
        # bboxes because we clamp, but let's test the list handling
        bboxes = [
            NormalizedBBox(x=0.1, y=0.1, width=0.2, height=0.3),
            NormalizedBBox(x=0.4, y=0.2, width=0.2, height=0.3),
        ]

        results = crop_multiple_bottles(image_bytes, bboxes)

        assert len(results) == 2
        assert all(r is not None for r in results)

    def test_returns_none_list_on_invalid_image(self):
        """Test that invalid image returns list of Nones."""
        bboxes = [
            NormalizedBBox(x=0.1, y=0.1, width=0.2, height=0.3),
            NormalizedBBox(x=0.4, y=0.2, width=0.2, height=0.3),
        ]

        results = crop_multiple_bottles(b"not an image", bboxes)

        assert len(results) == 2
        assert all(r is None for r in results)


class TestJpegQuality:
    """Tests for JPEG quality settings."""

    def test_high_quality_larger_than_low(self):
        """Test that higher quality produces larger files."""
        image_bytes = create_test_image(500, 500)
        bbox = NormalizedBBox(x=0.0, y=0.0, width=1.0, height=1.0)

        high_q = crop_bottle_region(image_bytes, bbox, jpeg_quality=95)
        low_q = crop_bottle_region(image_bytes, bbox, jpeg_quality=50)

        assert high_q is not None
        assert low_q is not None
        # Higher quality should produce larger file
        assert len(high_q.image_bytes) > len(low_q.image_bytes)
