#!/usr/bin/env python3
"""
Speed test: Claude 3.5 Haiku vs Claude 3.5 Sonnet for wine identification from shelf photo.

Usage:
    cd backend && source venv313/bin/activate
    python scripts/test_claude_speed.py
"""

import base64
import json
import os
import time
from pathlib import Path

import anthropic

# Configuration
IMAGE_PATH = Path(__file__).parent.parent.parent / "test-images" / "IMG_8080.jpg"
MODELS = [
    ("claude-3-5-haiku-latest", "Claude 3.5 Haiku"),
    ("claude-sonnet-4-20250514", "Claude Sonnet 4"),
]

PROMPT = """Analyze this wine shelf photo. Identify every wine bottle you can see.

For each bottle, return:
- wine_name: the full wine name including producer, varietal, and vintage if visible
- confidence: your confidence in the identification (0.0 to 1.0)
- estimated_rating: estimated rating on a 5-point scale (e.g., 4.2)
- bbox: bounding box as normalized 0-1 coordinates {x, y, width, height} where (x,y) is the top-left corner

Return ONLY valid JSON in this exact format, no other text:
{
  "wines": [
    {
      "wine_name": "Example Winery Cabernet Sauvignon 2020",
      "confidence": 0.85,
      "estimated_rating": 4.3,
      "bbox": {"x": 0.1, "y": 0.2, "width": 0.08, "height": 0.6}
    }
  ]
}"""


def load_image(path: Path) -> str:
    """Load image and return base64-encoded string."""
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def test_model(client: anthropic.Anthropic, model_id: str, model_name: str, image_b64: str) -> dict:
    """Send image to a Claude model and measure timing."""
    print(f"\n{'='*60}")
    print(f"Testing: {model_name} ({model_id})")
    print(f"{'='*60}")

    start = time.perf_counter()

    message = client.messages.create(
        model=model_id,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": PROMPT,
                    },
                ],
            }
        ],
    )

    elapsed = time.perf_counter() - start

    # Extract response text
    raw_text = message.content[0].text

    # Parse JSON from response (handle markdown code blocks)
    json_text = raw_text
    if "```json" in json_text:
        json_text = json_text.split("```json")[1].split("```")[0]
    elif "```" in json_text:
        json_text = json_text.split("```")[1].split("```")[0]

    try:
        result = json.loads(json_text.strip())
        wines = result.get("wines", [])
    except json.JSONDecodeError:
        print(f"  WARNING: Failed to parse JSON response")
        print(f"  Raw response:\n{raw_text[:500]}")
        wines = []

    # Print results
    print(f"\n  Time: {elapsed:.2f}s")
    print(f"  Wines found: {len(wines)}")
    print(f"  Input tokens: {message.usage.input_tokens}")
    print(f"  Output tokens: {message.usage.output_tokens}")

    if wines:
        print(f"\n  Wines identified:")
        for i, wine in enumerate(wines, 1):
            name = wine.get("wine_name", "Unknown")
            conf = wine.get("confidence", 0)
            rating = wine.get("estimated_rating", "N/A")
            bbox = wine.get("bbox", {})
            print(f"    {i}. {name}")
            print(f"       confidence={conf:.2f}, rating={rating}, bbox={bbox}")

    return {
        "model": model_name,
        "model_id": model_id,
        "elapsed_s": elapsed,
        "wines_found": len(wines),
        "wines": wines,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }


def main():
    # Validate image
    if not IMAGE_PATH.exists():
        print(f"ERROR: Image not found at {IMAGE_PATH}")
        return

    print(f"Image: {IMAGE_PATH} ({IMAGE_PATH.stat().st_size / 1024:.0f} KB)")

    # Load image once
    image_b64 = load_image(IMAGE_PATH)
    print(f"Base64 size: {len(image_b64) / 1024:.0f} KB")

    # Initialize client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        return

    client = anthropic.Anthropic(api_key=api_key)

    # Test each model
    results = []
    for model_id, model_name in MODELS:
        result = test_model(client, model_id, model_name, image_b64)
        results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"{'Model':<25} {'Time':>8} {'Wines':>7} {'In Tokens':>11} {'Out Tokens':>11}")
    print(f"{'-'*25} {'-'*8} {'-'*7} {'-'*11} {'-'*11}")
    for r in results:
        print(
            f"{r['model']:<25} {r['elapsed_s']:>7.2f}s {r['wines_found']:>7} "
            f"{r['input_tokens']:>11} {r['output_tokens']:>11}"
        )

    # Speed comparison
    if len(results) == 2 and results[0]["elapsed_s"] > 0:
        ratio = results[1]["elapsed_s"] / results[0]["elapsed_s"]
        faster = results[0]["model"] if ratio > 1 else results[1]["model"]
        factor = max(ratio, 1 / ratio)
        print(f"\n{faster} is {factor:.1f}x faster")


if __name__ == "__main__":
    main()
