#!/usr/bin/env python
"""
Pipeline benchmark tool.

Benchmarks different pipeline modes by running scans through the FastAPI
test client (no running server needed).

Usage:
    python scripts/pipeline_benchmark.py --pipeline turbo --images ../test-images/wine1.jpeg
    python scripts/pipeline_benchmark.py --pipeline all --images ../test-images/wine1.jpeg
    python scripts/pipeline_benchmark.py --pipeline all --images ../test-images/wine1.jpeg --json
    python scripts/pipeline_benchmark.py --pipeline legacy --images ../test-images/wine1.jpeg --runs 3

Note: GOOGLE_APPLICATION_CREDENTIALS must be set for real Vision API calls.
"""

import argparse
import asyncio
import json
import os
import sys
import statistics
import time
import traceback

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def run_single_benchmark(pipeline_mode: str, image_path: str) -> dict:
    """Run a single scan through the API with the given pipeline mode."""
    os.environ["PIPELINE_MODE"] = pipeline_mode

    # Import after setting env vars so config picks them up
    from httpx import AsyncClient, ASGITransport
    from main import app, set_ready

    # Mark app as ready (lifespan events don't fire with ASGITransport)
    set_ready(True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        # Determine content type from extension
        ext = os.path.splitext(image_path)[1].lower()
        content_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".heic": "image/heic",
            ".heif": "image/heif",
        }
        content_type = content_types.get(ext, "image/jpeg")

        start = time.perf_counter()
        response = await client.post(
            "/scan",
            files={"image": ("test" + ext, image_bytes, content_type)},
            params={"debug": "true"},
            timeout=60.0,
        )
        elapsed = time.perf_counter() - start

        data = response.json()
        return {
            "pipeline": pipeline_mode,
            "image": os.path.basename(image_path),
            "time_s": round(elapsed, 2),
            "status": response.status_code,
            "results_count": len(data.get("results", [])),
            "fallback_count": len(data.get("fallback_list", [])),
            "wines": [r["wine_name"] for r in data.get("results", [])],
        }


async def benchmark_pipeline(
    pipeline_mode: str, image_paths: list, runs: int = 1
) -> dict:
    """Benchmark a pipeline across multiple images and runs."""
    all_results = []
    for image_path in image_paths:
        for run_num in range(runs):
            try:
                result = await run_single_benchmark(pipeline_mode, image_path)
                all_results.append(result)
                print(
                    f"  {pipeline_mode}: {result['time_s']}s - "
                    f"{result['results_count']} results "
                    f"({os.path.basename(image_path)}, run {run_num + 1})"
                )
            except Exception as e:
                print(
                    f"  {pipeline_mode}: ERROR - {e} "
                    f"({os.path.basename(image_path)}, run {run_num + 1})"
                )
                traceback.print_exc()
                all_results.append(
                    {
                        "pipeline": pipeline_mode,
                        "image": os.path.basename(image_path),
                        "time_s": 0,
                        "status": 0,
                        "results_count": 0,
                        "fallback_count": 0,
                        "wines": [],
                        "error": str(e),
                    }
                )

    successful = [r for r in all_results if "error" not in r]
    if not successful:
        return {
            "pipeline": pipeline_mode,
            "runs": len(all_results),
            "error": "All runs failed",
            "details": all_results,
        }

    times = [r["time_s"] for r in successful]
    sorted_times = sorted(times)
    p95_idx = int(len(sorted_times) * 0.95)
    p95_idx = min(p95_idx, len(sorted_times) - 1)

    return {
        "pipeline": pipeline_mode,
        "runs": len(all_results),
        "successful_runs": len(successful),
        "avg_time_s": round(statistics.mean(times), 2),
        "p50_time_s": round(statistics.median(times), 2),
        "p95_time_s": round(sorted_times[p95_idx], 2),
        "min_time_s": round(min(times), 2),
        "max_time_s": round(max(times), 2),
        "avg_results": round(
            statistics.mean(r["results_count"] for r in successful), 1
        ),
        "details": all_results,
    }


def print_comparison_table(summaries: list):
    """Print a formatted comparison table."""
    print("\n" + "=" * 80)
    print(
        f"{'Pipeline':<12} {'Avg(s)':<8} {'P50(s)':<8} {'P95(s)':<8} "
        f"{'Min(s)':<8} {'Max(s)':<8} {'Results':<8}"
    )
    print("-" * 80)
    for s in summaries:
        if "error" in s:
            print(f"{s['pipeline']:<12} {'FAILED':<8} {s.get('error', '')}")
        else:
            print(
                f"{s['pipeline']:<12} {s['avg_time_s']:<8} {s['p50_time_s']:<8} "
                f"{s['p95_time_s']:<8} {s['min_time_s']:<8} {s['max_time_s']:<8} "
                f"{s['avg_results']:<8}"
            )
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Benchmark wine scanner pipelines")
    parser.add_argument(
        "--pipeline",
        choices=["legacy", "turbo", "hybrid", "fast", "all"],
        default="all",
        help="Pipeline mode to benchmark (default: all)",
    )
    parser.add_argument(
        "--images",
        nargs="+",
        required=True,
        help="Image paths to benchmark",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of runs per image (default: 1)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    # Validate image paths
    for img in args.images:
        if not os.path.exists(img):
            print(f"Error: Image not found: {img}")
            sys.exit(1)

    pipelines = (
        ["legacy", "turbo", "hybrid", "fast"]
        if args.pipeline == "all"
        else [args.pipeline]
    )

    summaries = []
    for pipeline in pipelines:
        print(f"\nBenchmarking {pipeline} pipeline...")
        summary = asyncio.run(benchmark_pipeline(pipeline, args.images, args.runs))
        summaries.append(summary)

    if args.json:
        print(json.dumps(summaries, indent=2))
    else:
        print_comparison_table(summaries)


if __name__ == "__main__":
    main()
