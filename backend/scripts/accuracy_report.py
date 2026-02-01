#!/usr/bin/env python3
"""
Wine Recognition Accuracy Report CLI

Evaluates pipeline performance against ground truth corpus.

Usage:
    python scripts/accuracy_report.py --corpus test-images/corpus/
    python scripts/accuracy_report.py --image test-images/corpus/shelf_01.jpg
    python scripts/accuracy_report.py --corpus test-images/corpus/ --generate-stubs
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.accuracy.metrics import (
    AccuracyMetrics,
    evaluate_results,
    aggregate_metrics,
)


def load_ground_truth(gt_path: Path) -> dict:
    """Load ground truth JSON file."""
    with open(gt_path) as f:
        return json.load(f)


def find_ground_truth(image_path: Path, corpus_dir: Path) -> Path | None:
    """Find ground truth file for an image."""
    gt_dir = corpus_dir / "ground_truth"
    gt_name = image_path.stem + ".json"
    gt_path = gt_dir / gt_name
    return gt_path if gt_path.exists() else None


def generate_ground_truth_stub(image_path: Path, results: list[dict]) -> dict:
    """Generate a ground truth stub from pipeline results."""
    wines = []
    for r in results:
        wines.append({
            "wine_name": r.get("wine_name", ""),
            "expected_rating": r.get("rating"),
            "rating_tolerance": 0.5,
            "notes": "Auto-generated - verify and correct"
        })

    return {
        "image_file": image_path.name,
        "wines": wines,
        "total_visible_bottles": len(wines),
        "notes": "Auto-generated stub - needs manual verification"
    }


async def run_pipeline_on_image(image_path: Path, use_llm: bool = True) -> list[dict]:
    """
    Run the recognition pipeline on a single image.

    Returns list of detected wines with wine_name, rating, rating_source.
    """
    from app.services.recognition_pipeline import RecognitionPipeline
    from app.services.ocr_processor import OCRProcessor
    from app.services.vision import VisionService

    # Read image
    with open(image_path, "rb") as f:
        image_data = f.read()

    # Run Vision API (or mock)
    vision = VisionService()
    vision_result = await vision.analyze_image(image_data)

    # Process OCR
    ocr = OCRProcessor()
    bottle_texts = ocr.process(
        vision_result.text_annotations,
        vision_result.object_annotations,
        image_width=vision_result.image_width or 1000,
        image_height=vision_result.image_height or 1000
    )

    # Run recognition pipeline
    pipeline = RecognitionPipeline(use_llm=use_llm)
    recognized = await pipeline.recognize(bottle_texts)

    # Convert to dict format for evaluation
    results = []
    for wine in recognized:
        results.append({
            "wine_name": wine.wine_name,
            "rating": wine.rating,
            "rating_source": getattr(wine, "rating_source", "database"),
            "confidence": wine.confidence,
            "source": wine.source,
        })

    return results


async def evaluate_image(
    image_path: Path,
    ground_truth: dict,
    use_llm: bool = True
) -> AccuracyMetrics:
    """Evaluate a single image against ground truth."""
    # Run pipeline
    results = await run_pipeline_on_image(image_path, use_llm=use_llm)

    # Convert ground truth to expected format
    gt_wines = ground_truth.get("wines", [])

    # Evaluate
    metrics = evaluate_results(results, gt_wines)

    return metrics


async def evaluate_corpus(
    corpus_dir: Path,
    use_llm: bool = True,
    verbose: bool = False
) -> AccuracyMetrics:
    """Evaluate all images in corpus with ground truth."""
    image_extensions = {".jpg", ".jpeg", ".png"}
    gt_dir = corpus_dir / "ground_truth"

    all_metrics = []
    images_processed = 0
    images_skipped = 0

    for image_path in corpus_dir.iterdir():
        if image_path.suffix.lower() not in image_extensions:
            continue

        # Find ground truth
        gt_path = gt_dir / (image_path.stem + ".json")
        if not gt_path.exists():
            if verbose:
                print(f"  Skipping {image_path.name} (no ground truth)")
            images_skipped += 1
            continue

        ground_truth = load_ground_truth(gt_path)

        if verbose:
            print(f"  Processing {image_path.name}...")

        try:
            metrics = await evaluate_image(image_path, ground_truth, use_llm=use_llm)
            all_metrics.append(metrics)
            images_processed += 1

            if verbose:
                print(f"    TP={metrics.true_positives} FP={metrics.false_positives} FN={metrics.false_negatives}")

        except Exception as e:
            print(f"  Error processing {image_path.name}: {e}")
            images_skipped += 1

    if not all_metrics:
        print("No images processed successfully.")
        return AccuracyMetrics()

    # Aggregate results
    combined = aggregate_metrics(all_metrics)

    print(f"\nProcessed {images_processed} images, skipped {images_skipped}")

    return combined


async def generate_stubs(corpus_dir: Path, use_llm: bool = True) -> None:
    """Generate ground truth stubs for images without them."""
    image_extensions = {".jpg", ".jpeg", ".png"}
    gt_dir = corpus_dir / "ground_truth"
    gt_dir.mkdir(exist_ok=True)

    stubs_created = 0

    for image_path in corpus_dir.iterdir():
        if image_path.suffix.lower() not in image_extensions:
            continue

        gt_path = gt_dir / (image_path.stem + ".json")
        if gt_path.exists():
            print(f"  Skipping {image_path.name} (ground truth exists)")
            continue

        print(f"  Generating stub for {image_path.name}...")

        try:
            results = await run_pipeline_on_image(image_path, use_llm=use_llm)
            stub = generate_ground_truth_stub(image_path, results)

            with open(gt_path, "w") as f:
                json.dump(stub, f, indent=2)

            print(f"    Created {gt_path.name} with {len(results)} wines")
            stubs_created += 1

        except Exception as e:
            print(f"    Error: {e}")

    print(f"\nGenerated {stubs_created} ground truth stubs")


def main():
    parser = argparse.ArgumentParser(
        description="Wine Recognition Accuracy Report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/accuracy_report.py --corpus test-images/corpus/
    python scripts/accuracy_report.py --image test-images/corpus/shelf_01.jpg
    python scripts/accuracy_report.py --corpus test-images/corpus/ --generate-stubs
        """
    )

    parser.add_argument(
        "--corpus",
        type=Path,
        help="Path to corpus directory with images and ground_truth/"
    )
    parser.add_argument(
        "--image",
        type=Path,
        help="Path to single image to evaluate"
    )
    parser.add_argument(
        "--generate-stubs",
        action="store_true",
        help="Generate ground truth stubs for images without them"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM fallback (faster, but lower accuracy)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    if not args.corpus and not args.image:
        parser.error("Either --corpus or --image is required")

    use_llm = not args.no_llm

    async def run():
        if args.generate_stubs:
            if not args.corpus:
                parser.error("--generate-stubs requires --corpus")
            await generate_stubs(args.corpus, use_llm=use_llm)
            return

        if args.corpus:
            print(f"Evaluating corpus: {args.corpus}")
            metrics = await evaluate_corpus(args.corpus, use_llm=use_llm, verbose=args.verbose)
        else:
            # Single image mode
            gt_path = find_ground_truth(args.image, args.image.parent)
            if not gt_path:
                print(f"No ground truth found for {args.image.name}")
                print(f"Run with --generate-stubs to create one")
                return

            ground_truth = load_ground_truth(gt_path)
            metrics = await evaluate_image(args.image, ground_truth, use_llm=use_llm)

        # Output results
        if args.json:
            output = {
                "precision": metrics.precision,
                "recall": metrics.recall,
                "f1": metrics.f1,
                "true_positives": metrics.true_positives,
                "false_positives": metrics.false_positives,
                "false_negatives": metrics.false_negatives,
                "rating_mae_db": metrics.rating_mae_db,
                "rating_mae_llm": metrics.rating_mae_llm,
                "wines_with_ratings_pct": metrics.wines_with_ratings_pct,
            }
            print(json.dumps(output, indent=2))
        else:
            print()
            print(metrics.summary())

            # Show pass/fail vs targets
            print()
            print("Target Comparison")
            print("-" * 40)

            targets = [
                ("Precision", metrics.precision, 0.85),
                ("Recall", metrics.recall, 0.80),
                ("Rating MAE (DB)", metrics.rating_mae_db, 0.3) if metrics.rating_mae_db else None,
                ("Rating MAE (LLM)", metrics.rating_mae_llm, 0.75) if metrics.rating_mae_llm else None,
            ]

            for target in targets:
                if target is None:
                    continue
                name, value, threshold = target
                if "MAE" in name:
                    # Lower is better for MAE
                    passed = value <= threshold
                    symbol = "✓" if passed else "✗"
                    print(f"{symbol} {name}: {value:.3f} (target ≤ {threshold})")
                else:
                    # Higher is better for precision/recall
                    passed = value >= threshold
                    symbol = "✓" if passed else "✗"
                    print(f"{symbol} {name}: {value:.3f} (target ≥ {threshold})")

    asyncio.run(run())


if __name__ == "__main__":
    main()
