"""
Benchmark script for scan pipeline performance.
Tests IMG_8080.jpg against different pipeline modes and reports timing + bottle count.

Usage:
    cd backend && source venv/bin/activate
    python scripts/benchmark_scan.py [--mode turbo|fast|hybrid|legacy] [--image PATH]
"""

import argparse
import asyncio
import os
import sys
import time

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

# Ensure keys from env/ folder are available
env_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'env', '.env')
if os.path.exists(env_dir):
    load_dotenv(env_dir, override=True)


def run_benchmark(image_path: str, pipeline_mode: str):
    """Run a single benchmark."""
    # Set pipeline mode
    os.environ["PIPELINE_MODE"] = pipeline_mode
    os.environ["DEBUG_MODE"] = "true"
    os.environ["USE_LLM_CACHE"] = "true"
    os.environ["VISION_CACHE_ENABLED"] = "true"
    os.environ["LOG_LEVEL"] = "WARNING"  # Reduce noise

    # Import after env is set
    from app.routes.scan import process_image, get_wine_matcher
    from app.feature_flags import FeatureFlags

    # Read image
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    wine_matcher = get_wine_matcher()
    flags = FeatureFlags()

    print(f"\n{'='*60}")
    print(f"Pipeline mode: {pipeline_mode}")
    print(f"Image: {image_path} ({len(image_bytes) / 1024:.0f} KB)")
    print(f"{'='*60}")

    t0 = time.perf_counter()

    response = asyncio.run(process_image(
        image_id="benchmark",
        image_bytes=image_bytes,
        use_real_api=True,
        use_llm=True,
        use_vision_fallback=True,
        debug_mode=True,
        wine_matcher=wine_matcher,
        flags=flags,
    ))

    elapsed = time.perf_counter() - t0

    print(f"\nTotal time: {elapsed:.2f}s")
    print(f"Results (with bbox): {len(response.results)}")
    print(f"Fallback (no bbox):  {len(response.fallback_list)}")
    print(f"Total wines found:   {len(response.results) + len(response.fallback_list)}")
    print()

    # Print results
    for i, r in enumerate(response.results):
        src = r.source.value if r.source else "?"
        rsrc = r.rating_source.value if r.rating_source else "?"
        print(f"  {i+1:2d}. {r.wine_name:<50s} rating={r.rating}  conf={r.confidence:.2f}  src={src}/{rsrc}")

    if response.fallback_list:
        print("\n  Fallback:")
        for i, f in enumerate(response.fallback_list):
            print(f"  {i+1:2d}. {f.wine_name:<50s} rating={f.rating}")

    return {
        "mode": pipeline_mode,
        "elapsed": elapsed,
        "results": len(response.results),
        "fallback": len(response.fallback_list),
        "total": len(response.results) + len(response.fallback_list),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark wine scan pipeline")
    parser.add_argument("--mode", default="turbo", choices=["turbo", "fast", "hybrid", "flash_names", "legacy"])
    parser.add_argument("--image", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "test-images", "IMG_8080.jpg"
    ))
    args = parser.parse_args()

    result = run_benchmark(args.image, args.mode)
    print(f"\n{'='*60}")
    print(f"SUMMARY: mode={result['mode']}  time={result['elapsed']:.2f}s  "
          f"results={result['results']}  fallback={result['fallback']}  total={result['total']}")
