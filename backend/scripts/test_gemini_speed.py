#!/usr/bin/env python3
"""
Standalone speed test for Gemini Flash vision calls.

Tests multiple variants to isolate where latency comes from:
1. litellm + gemini-2.0-flash (current pipeline)
2. litellm + gemini-2.0-flash with more compressed image
3. litellm + gemini-2.0-flash-lite
4. google-genai SDK direct (no litellm overhead)
5. google-genai SDK direct + compressed image
6. google-genai SDK direct + gemini-2.0-flash-lite

Usage:
    source venv313/bin/activate
    python scripts/test_gemini_speed.py
"""

import asyncio
import base64
import io
import json
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Load .env from backend directory
backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(backend_dir / ".env")

# Add backend to path so we can import the prompt
sys.path.insert(0, str(backend_dir))
from app.services.fast_pipeline import FAST_PIPELINE_PROMPT

from PIL import Image

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    print("ERROR: GOOGLE_API_KEY not set in environment or .env")
    sys.exit(1)

IMAGE_PATH = backend_dir.parent / "test-images" / "IMG_8080.jpg"
if not IMAGE_PATH.exists():
    print(f"ERROR: Image not found at {IMAGE_PATH}")
    sys.exit(1)


def load_image() -> bytes:
    """Load the test image as-is."""
    return IMAGE_PATH.read_bytes()


def compress_image(image_bytes: bytes, quality: int = 50, max_dim: int = 800) -> bytes:
    """Compress image: resize to max_dim and save at given JPEG quality."""
    img = Image.open(io.BytesIO(image_bytes))
    # Resize keeping aspect ratio
    img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def count_wines(response_text: str) -> int:
    """Parse JSON response and count identified wines."""
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return len([w for w in data if isinstance(w, dict) and w.get("wine_name")])
    except json.JSONDecodeError:
        pass
    return 0


def print_header():
    """Print test header."""
    original = load_image()
    compressed = compress_image(original)
    print("=" * 80)
    print("GEMINI FLASH VISION SPEED TEST")
    print("=" * 80)
    print(f"Image:              {IMAGE_PATH.name}")
    print(f"Original size:      {len(original):,} bytes ({len(original)/1024:.0f} KB)")
    print(f"Original dims:      {Image.open(io.BytesIO(original)).size}")
    print(f"Compressed size:    {len(compressed):,} bytes ({len(compressed)/1024:.0f} KB)")
    print(f"Compressed dims:    {Image.open(io.BytesIO(compressed)).size}")
    print(f"Prompt length:      {len(FAST_PIPELINE_PROMPT)} chars")
    print(f"API Key:            ...{GOOGLE_API_KEY[-8:]}")
    print("=" * 80)
    print()


# ---------------------------------------------------------------------------
# Test 1-3: litellm variants
# ---------------------------------------------------------------------------

async def test_litellm(image_bytes: bytes, model: str, label: str) -> dict:
    """Test using litellm (matches current pipeline)."""
    import litellm
    litellm.set_verbose = False

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    t0 = time.perf_counter()
    try:
        response = await litellm.acompletion(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}",
                            },
                        },
                        {
                            "type": "text",
                            "text": FAST_PIPELINE_PROMPT,
                        },
                    ],
                }
            ],
            max_tokens=4000,
            temperature=0.1,
        )
        elapsed = time.perf_counter() - t0
        content = response.choices[0].message.content
        wines = count_wines(content)
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", "?") if usage else "?"
        completion_tokens = getattr(usage, "completion_tokens", "?") if usage else "?"
        return {
            "label": label,
            "elapsed_s": elapsed,
            "wines": wines,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "error": None,
        }
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return {
            "label": label,
            "elapsed_s": elapsed,
            "wines": 0,
            "prompt_tokens": "?",
            "completion_tokens": "?",
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Test 4-6: google-genai SDK direct
# ---------------------------------------------------------------------------

async def test_genai_direct(image_bytes: bytes, model_name: str, label: str) -> dict:
    """Test using google-genai SDK directly (bypass litellm)."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GOOGLE_API_KEY)

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    t0 = time.perf_counter()
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(
                            data=image_bytes,
                            mime_type="image/jpeg",
                        ),
                        types.Part.from_text(text=FAST_PIPELINE_PROMPT),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                max_output_tokens=4000,
                temperature=0.1,
            ),
        )
        elapsed = time.perf_counter() - t0
        content = response.text
        wines = count_wines(content)
        usage = response.usage_metadata
        prompt_tokens = getattr(usage, "prompt_tokens", "?") if usage else "?"
        completion_tokens = getattr(usage, "candidates_token_count", "?") if usage else "?"
        return {
            "label": label,
            "elapsed_s": elapsed,
            "wines": wines,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "error": None,
        }
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return {
            "label": label,
            "elapsed_s": elapsed,
            "wines": 0,
            "prompt_tokens": "?",
            "completion_tokens": "?",
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

async def main():
    print_header()

    original = load_image()
    compressed = compress_image(original, quality=50, max_dim=800)

    tests = [
        # (coroutine_factory, label)
        ("litellm", original, "gemini/gemini-2.0-flash", "1. litellm + gemini-2.0-flash (original 157KB)"),
        ("litellm", compressed, "gemini/gemini-2.0-flash", "2. litellm + gemini-2.0-flash (compressed)"),
        ("litellm", original, "gemini/gemini-2.0-flash-lite", "3. litellm + gemini-2.0-flash-lite (original)"),
        ("genai", original, "gemini-2.0-flash", "4. google-genai direct + gemini-2.0-flash (original)"),
        ("genai", compressed, "gemini-2.0-flash", "5. google-genai direct + gemini-2.0-flash (compressed)"),
        ("genai", original, "gemini-2.0-flash-lite", "6. google-genai direct + gemini-2.0-flash-lite (original)"),
    ]

    results = []

    for sdk, img, model, label in tests:
        print(f"Running: {label} ...")
        if sdk == "litellm":
            result = await test_litellm(img, model, label)
        else:
            result = await test_genai_direct(img, model, label)

        if result["error"]:
            print(f"  ERROR: {result['error']}")
        else:
            print(
                f"  {result['elapsed_s']:.2f}s | "
                f"{result['wines']} wines | "
                f"tokens: {result['prompt_tokens']} in / {result['completion_tokens']} out"
            )
        results.append(result)
        print()

    # Summary table
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'Test':<58} {'Time':>7} {'Wines':>6} {'Error'}")
    print("-" * 80)
    for r in results:
        err = r["error"][:15] + "..." if r["error"] and len(r["error"]) > 18 else (r["error"] or "")
        print(
            f"{r['label']:<58} "
            f"{r['elapsed_s']:>6.2f}s "
            f"{r['wines']:>5} "
            f"{err}"
        )
    print("-" * 80)

    # Find fastest
    successful = [r for r in results if not r["error"]]
    if successful:
        fastest = min(successful, key=lambda r: r["elapsed_s"])
        slowest = max(successful, key=lambda r: r["elapsed_s"])
        print(f"\nFastest: {fastest['label']} ({fastest['elapsed_s']:.2f}s)")
        print(f"Slowest: {slowest['label']} ({slowest['elapsed_s']:.2f}s)")
        print(f"Spread:  {slowest['elapsed_s'] - fastest['elapsed_s']:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
