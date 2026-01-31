#!/usr/bin/env python3
"""
Capture Vision API responses for test images.

This script calls the real Vision API and saves the response as JSON,
allowing tests to replay responses without making API calls.

Usage:
    python scripts/capture_vision_response.py ../test-images/wine1.jpeg
    # Creates: tests/fixtures/vision_responses/wine1_jpeg.json
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.vision import VisionService


def sanitize_filename(path: Path) -> str:
    """Convert image filename to safe fixture name."""
    # wine1.jpeg -> wine1_jpeg
    # wine-photos.jpg -> wine_photos_jpg
    name = path.name
    name = name.replace(".", "_").replace("-", "_")
    return name


def capture_response(image_path: Path, output_dir: Path) -> Path:
    """Capture Vision API response for an image."""
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Read image
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    print(f"Analyzing {image_path.name}...")

    # Call Vision API
    vision = VisionService()
    result = vision.analyze(image_bytes)

    # Convert to serializable dict
    response_data = {
        "image_file": image_path.name,
        "objects": [
            {
                "name": obj.name,
                "score": obj.confidence,
                "bbox": {
                    "x": obj.bbox.x,
                    "y": obj.bbox.y,
                    "width": obj.bbox.width,
                    "height": obj.bbox.height,
                }
            }
            for obj in result.objects
        ],
        "text_blocks": [
            {
                "text": block.text,
                "bbox": {
                    "x": block.bbox.x,
                    "y": block.bbox.y,
                    "width": block.bbox.width,
                    "height": block.bbox.height,
                } if block.bbox else None,
                "confidence": block.confidence,
            }
            for block in result.text_blocks
        ],
        "raw_text": result.raw_text,
    }

    # Save to fixture
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{sanitize_filename(image_path)}.json"

    with open(output_file, "w") as f:
        json.dump(response_data, f, indent=2)

    print(f"Saved to {output_file}")
    print(f"  Objects: {len(response_data['objects'])}")
    print(f"  Text blocks: {len(response_data['text_blocks'])}")

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Capture Vision API responses for test images"
    )
    parser.add_argument(
        "image",
        type=Path,
        help="Path to image file"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent / "tests" / "fixtures" / "vision_responses",
        help="Output directory for fixtures"
    )

    args = parser.parse_args()

    try:
        output_file = capture_response(args.image, args.output_dir)
        print(f"\nCapture complete: {output_file}")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error capturing response: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
