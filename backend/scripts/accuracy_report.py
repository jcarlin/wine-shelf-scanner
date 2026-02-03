#!/usr/bin/env python3
"""
Wine Recognition Accuracy Report CLI

Evaluates pipeline performance against ground truth corpus with detailed
failure analysis and iteration tracking for continuous improvement.

Usage:
    python scripts/accuracy_report.py --corpus test-images/corpus/labels/
    python scripts/accuracy_report.py --image test-images/corpus/labels/100062.jpeg
    python scripts/accuracy_report.py --corpus test-images/corpus/labels/ --generate-stubs
    python scripts/accuracy_report.py --corpus test-images/corpus/labels/ --analyze-failures
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# Load environment variables from .env before any other imports
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.accuracy.metrics import (
    AccuracyMetrics,
    evaluate_results,
    aggregate_metrics,
    normalize_wine_name,
)


# Failure categories for analysis
class FailureCategory:
    OCR_ERROR = "ocr_error"           # Text extraction failed
    MATCHING_ERROR = "matching_error"  # Right text, wrong match
    THRESHOLD_HIGH = "threshold_high"  # Correct match filtered out
    THRESHOLD_LOW = "threshold_low"    # Wrong match accepted
    NOT_IN_DB = "not_in_db"           # Wine not found in database
    MULTIPLE_WINES = "multiple_wines"  # Multiple wines detected as one
    UNKNOWN = "unknown"


@dataclass
class FailureDetail:
    """Detailed failure information for analysis."""
    image_file: str
    category: str
    expected_wine: str
    detected_wine: Optional[str]
    ocr_text: Optional[str] = None
    confidence: Optional[float] = None
    match_score: Optional[float] = None
    notes: str = ""


@dataclass
class ImageResult:
    """Results for a single image evaluation."""
    image_file: str
    ground_truth_wines: list[str]
    detected_wines: list[dict]
    true_positives: int
    false_positives: int
    false_negatives: int
    failures: list[FailureDetail] = field(default_factory=list)
    ocr_text: Optional[str] = None
    processing_time_ms: Optional[float] = None


@dataclass
class IterationResult:
    """Results from a full iteration run."""
    iteration: int
    timestamp: str
    metrics: dict
    targets_met: bool
    images_processed: int
    images_skipped: int
    image_results: list[ImageResult]
    failure_summary: dict
    notes: str = ""


def load_ground_truth(gt_path: Path) -> dict:
    """Load ground truth JSON file."""
    with open(gt_path) as f:
        return json.load(f)


def find_ground_truth(image_path: Path, corpus_dir: Path) -> Optional[Path]:
    """Find ground truth file for an image."""
    gt_dir = corpus_dir / "ground_truth"
    if not gt_dir.exists():
        gt_dir = corpus_dir.parent / "ground_truth"
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


async def run_pipeline_on_image(
    image_path: Path,
    use_llm: bool = True,
    collect_debug: bool = False
) -> tuple[list[dict], Optional[str]]:
    """
    Run the recognition pipeline on a single image.

    Returns tuple of (detected wines list, raw OCR text if debug enabled).
    """
    import time
    from app.services.recognition_pipeline import RecognitionPipeline
    from app.services.ocr_processor import OCRProcessor
    from app.services.vision import VisionService

    # Read image
    with open(image_path, "rb") as f:
        image_data = f.read()

    start_time = time.time()

    # Run Vision API (or mock)
    vision = VisionService()
    vision_result = vision.analyze(image_data)

    # Process OCR
    ocr = OCRProcessor()

    if vision_result.objects:
        # Normal path: bottles detected
        bottle_texts = ocr.process(
            vision_result.objects,  # bottles
            vision_result.text_blocks  # text
        )
    else:
        # No bottles detected - try direct OCR match
        # This handles close-up label shots
        from app.services.ocr_processor import BottleText
        from app.services.vision import DetectedObject, BoundingBox

        all_text = ' '.join([tb.text for tb in vision_result.text_blocks])
        normalized_text = ocr._normalize_text(all_text)

        if all_text and len(normalized_text.strip()) >= 3:
            synthetic_bottle = DetectedObject(
                name="Bottle",
                confidence=0.9,
                bbox=BoundingBox(x=0.0, y=0.0, width=1.0, height=1.0)
            )
            bottle_texts = [BottleText(
                bottle=synthetic_bottle,
                text_fragments=[all_text],
                combined_text=all_text,
                normalized_name=normalized_text
            )]
        else:
            bottle_texts = []

    # Run recognition pipeline with configured LLM provider
    from app.config import Config
    pipeline = RecognitionPipeline(use_llm=use_llm, llm_provider=Config.llm_provider())
    recognized = await pipeline.recognize(bottle_texts)

    elapsed_ms = (time.time() - start_time) * 1000

    # Convert to dict format for evaluation
    results = []
    seen_wines = set()
    for wine in recognized:
        # Deduplicate by wine name (same wine from multiple bottles)
        wine_key = wine.wine_name.lower().strip()
        if wine_key in seen_wines:
            continue
        seen_wines.add(wine_key)

        results.append({
            "wine_name": wine.wine_name,
            "rating": wine.rating,
            "rating_source": getattr(wine, "rating_source", "database"),
            "confidence": wine.confidence,
            "source": wine.source,
            "processing_time_ms": elapsed_ms,
        })

    # Collect raw OCR text if debug mode
    raw_ocr = None
    if collect_debug and vision_result.text_blocks:
        raw_ocr = " | ".join([t.text for t in vision_result.text_blocks[:10]])

    return results, raw_ocr


def categorize_failure(
    expected_wine: str,
    detected_wines: list[dict],
    ocr_text: Optional[str]
) -> FailureCategory:
    """
    Categorize a failure (false negative) by likely cause.

    Args:
        expected_wine: The wine name from ground truth that wasn't detected
        detected_wines: List of all detected wines
        ocr_text: Raw OCR text from the image

    Returns:
        Best-guess failure category
    """
    from rapidfuzz import fuzz

    expected_norm = normalize_wine_name(expected_wine)

    # Check if wine name appears in OCR text
    ocr_has_wine = False
    if ocr_text:
        ocr_norm = ocr_text.lower()
        # Check for key words from wine name
        key_words = [w for w in expected_norm.split() if len(w) > 3]
        matches = sum(1 for w in key_words if w in ocr_norm)
        if matches >= len(key_words) * 0.5:
            ocr_has_wine = True

    # Check if any detected wine is similar
    best_match_score = 0.0
    for detected in detected_wines:
        detected_norm = normalize_wine_name(detected.get("wine_name", ""))
        score = fuzz.token_sort_ratio(expected_norm, detected_norm) / 100.0
        best_match_score = max(best_match_score, score)

    # Categorize based on evidence
    if best_match_score >= 0.6:
        # Similar wine was detected but not matched
        if best_match_score >= 0.75:
            return FailureCategory.THRESHOLD_HIGH
        return FailureCategory.MATCHING_ERROR

    if not ocr_has_wine and ocr_text:
        return FailureCategory.OCR_ERROR

    if ocr_has_wine:
        # OCR found it but matcher didn't
        return FailureCategory.NOT_IN_DB

    return FailureCategory.UNKNOWN


def analyze_failures(
    image_results: list[ImageResult]
) -> dict:
    """
    Analyze all failures and generate summary statistics.

    Returns dict with failure counts by category and examples.
    """
    failure_counts = {
        FailureCategory.OCR_ERROR: 0,
        FailureCategory.MATCHING_ERROR: 0,
        FailureCategory.THRESHOLD_HIGH: 0,
        FailureCategory.THRESHOLD_LOW: 0,
        FailureCategory.NOT_IN_DB: 0,
        FailureCategory.MULTIPLE_WINES: 0,
        FailureCategory.UNKNOWN: 0,
    }

    examples_by_category: dict[str, list[dict]] = {k: [] for k in failure_counts}

    for result in image_results:
        for failure in result.failures:
            failure_counts[failure.category] = failure_counts.get(failure.category, 0) + 1

            # Keep up to 5 examples per category
            if len(examples_by_category[failure.category]) < 5:
                examples_by_category[failure.category].append({
                    "image": failure.image_file,
                    "expected": failure.expected_wine,
                    "detected": failure.detected_wine,
                    "ocr_text": failure.ocr_text[:100] if failure.ocr_text else None,
                    "confidence": failure.confidence,
                })

    return {
        "counts": failure_counts,
        "total_failures": sum(failure_counts.values()),
        "examples": examples_by_category,
    }


async def evaluate_image_detailed(
    image_path: Path,
    ground_truth: dict,
    use_llm: bool = True
) -> ImageResult:
    """Evaluate a single image with detailed failure analysis."""
    import time
    from rapidfuzz import fuzz

    start_time = time.time()

    # Run pipeline with debug info
    results, ocr_text = await run_pipeline_on_image(
        image_path, use_llm=use_llm, collect_debug=True
    )

    elapsed_ms = (time.time() - start_time) * 1000

    # Get ground truth wines
    gt_wines = ground_truth.get("wines", [])
    gt_wine_names = [w.get("wine_name", "") for w in gt_wines]

    # Evaluate using standard metrics
    metrics = evaluate_results(results, gt_wines)

    # Build detailed failures list
    failures = []

    # Track which ground truth wines were matched
    matched_gt = set()
    for match in metrics.matches:
        if match.is_name_match:
            matched_gt.add(match.ground_truth_name)

    # Analyze false negatives (missed wines)
    for gt_wine in gt_wines:
        gt_name = gt_wine.get("wine_name", "")
        if gt_name not in matched_gt:
            category = categorize_failure(gt_name, results, ocr_text)
            failures.append(FailureDetail(
                image_file=image_path.name,
                category=category,
                expected_wine=gt_name,
                detected_wine=None,
                ocr_text=ocr_text,
                notes=f"False negative - {category}"
            ))

    # Analyze false positives (wrong detections)
    for match in metrics.matches:
        if not match.is_name_match and match.detected_name:
            # Check if it's a threshold issue
            best_score = 0.0
            best_gt = ""
            for gt_name in gt_wine_names:
                score = fuzz.token_sort_ratio(
                    normalize_wine_name(match.detected_name),
                    normalize_wine_name(gt_name)
                ) / 100.0
                if score > best_score:
                    best_score = score
                    best_gt = gt_name

            if best_score >= 0.6:
                category = FailureCategory.THRESHOLD_LOW
            else:
                category = FailureCategory.MATCHING_ERROR

            failures.append(FailureDetail(
                image_file=image_path.name,
                category=category,
                expected_wine=best_gt if best_score >= 0.5 else "",
                detected_wine=match.detected_name,
                match_score=best_score,
                notes=f"False positive - {category}"
            ))

    return ImageResult(
        image_file=image_path.name,
        ground_truth_wines=gt_wine_names,
        detected_wines=results,
        true_positives=metrics.true_positives,
        false_positives=metrics.false_positives,
        false_negatives=metrics.false_negatives,
        failures=failures,
        ocr_text=ocr_text,
        processing_time_ms=elapsed_ms,
    )


async def evaluate_corpus_detailed(
    corpus_dir: Path,
    use_llm: bool = True,
    verbose: bool = False,
    max_images: Optional[int] = None
) -> tuple[AccuracyMetrics, list[ImageResult]]:
    """
    Evaluate all images in corpus with detailed failure tracking.

    Args:
        corpus_dir: Path to corpus directory (can be labels/ or corpus/)
        use_llm: Whether to use LLM fallback
        verbose: Print progress
        max_images: Limit number of images (for quick testing)

    Returns:
        Tuple of (aggregated metrics, list of per-image results)
    """
    image_extensions = {".jpg", ".jpeg", ".png"}

    # Handle corpus_dir being either the labels/ subdir or the corpus/ parent
    if corpus_dir.name == "labels":
        gt_dir = corpus_dir.parent / "ground_truth"
    else:
        gt_dir = corpus_dir / "ground_truth"

    all_metrics = []
    image_results = []
    images_processed = 0
    images_skipped = 0

    # Find images to process
    image_paths = [
        p for p in corpus_dir.iterdir()
        if p.suffix.lower() in image_extensions
    ]

    if max_images:
        image_paths = image_paths[:max_images]

    for image_path in image_paths:
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
            result = await evaluate_image_detailed(
                image_path, ground_truth, use_llm=use_llm
            )
            image_results.append(result)

            # Create metrics object for aggregation
            metrics = AccuracyMetrics()
            metrics.true_positives = result.true_positives
            metrics.false_positives = result.false_positives
            metrics.false_negatives = result.false_negatives
            all_metrics.append(metrics)

            images_processed += 1

            if verbose:
                status = "OK" if result.false_negatives == 0 else "FAIL"
                print(f"    [{status}] TP={result.true_positives} FP={result.false_positives} FN={result.false_negatives}")

        except Exception as e:
            print(f"  Error processing {image_path.name}: {e}")
            import traceback
            if verbose:
                traceback.print_exc()
            images_skipped += 1

    if not all_metrics:
        print("No images processed successfully.")
        return AccuracyMetrics(), []

    # Aggregate results
    combined = aggregate_metrics(all_metrics)

    print(f"\nProcessed {images_processed} images, skipped {images_skipped}")

    return combined, image_results


async def evaluate_image(
    image_path: Path,
    ground_truth: dict,
    use_llm: bool = True
) -> AccuracyMetrics:
    """Evaluate a single image against ground truth (simple mode)."""
    results, _ = await run_pipeline_on_image(image_path, use_llm=use_llm)
    gt_wines = ground_truth.get("wines", [])
    metrics = evaluate_results(results, gt_wines)
    return metrics


async def evaluate_corpus(
    corpus_dir: Path,
    use_llm: bool = True,
    verbose: bool = False
) -> AccuracyMetrics:
    """Evaluate all images in corpus with ground truth (simple mode)."""
    metrics, _ = await evaluate_corpus_detailed(
        corpus_dir, use_llm=use_llm, verbose=verbose
    )
    return metrics


async def generate_stubs(corpus_dir: Path, use_llm: bool = True) -> None:
    """Generate ground truth stubs for images without them."""
    image_extensions = {".jpg", ".jpeg", ".png"}

    # Handle corpus_dir being labels/ or corpus/
    if corpus_dir.name == "labels":
        gt_dir = corpus_dir.parent / "ground_truth"
    else:
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
            results, _ = await run_pipeline_on_image(image_path, use_llm=use_llm)
            stub = generate_ground_truth_stub(image_path, results)

            with open(gt_path, "w") as f:
                json.dump(stub, f, indent=2)

            print(f"    Created {gt_path.name} with {len(results)} wines")
            stubs_created += 1

        except Exception as e:
            print(f"    Error: {e}")

    print(f"\nGenerated {stubs_created} ground truth stubs")


def load_iteration_log(log_path: Path) -> dict:
    """Load iteration log or create empty structure."""
    if log_path.exists():
        with open(log_path) as f:
            return json.load(f)
    return {"iterations": []}


def save_iteration_log(log_path: Path, log_data: dict) -> None:
    """Save iteration log."""
    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2)


def check_targets_met(metrics: AccuracyMetrics) -> tuple[bool, dict]:
    """
    Check if accuracy targets are met.

    Returns:
        Tuple of (all_met, results_dict)
    """
    targets = {
        "precision": {"value": metrics.precision, "target": 0.85, "higher_better": True},
        "recall": {"value": metrics.recall, "target": 0.80, "higher_better": True},
        "f1": {"value": metrics.f1, "target": 0.82, "higher_better": True},
    }

    results = {}
    all_met = True

    for name, t in targets.items():
        if t["higher_better"]:
            met = t["value"] >= t["target"]
        else:
            met = t["value"] <= t["target"]

        results[name] = {
            "value": t["value"],
            "target": t["target"],
            "met": met
        }

        if not met:
            all_met = False

    return all_met, results


def main():
    parser = argparse.ArgumentParser(
        description="Wine Recognition Accuracy Report with Failure Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic evaluation
    python scripts/accuracy_report.py --corpus test-images/corpus/labels/

    # With detailed failure analysis
    python scripts/accuracy_report.py --corpus test-images/corpus/labels/ --analyze-failures

    # Quick test with 10 images
    python scripts/accuracy_report.py --corpus test-images/corpus/labels/ --max-images 10

    # Generate stubs for new images
    python scripts/accuracy_report.py --corpus test-images/corpus/labels/ --generate-stubs

    # Export results to JSON
    python scripts/accuracy_report.py --corpus test-images/corpus/labels/ --json --analyze-failures > results.json
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
        "--analyze-failures",
        action="store_true",
        help="Perform detailed failure analysis"
    )
    parser.add_argument(
        "--max-images",
        type=int,
        help="Limit number of images to process (for quick testing)"
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
    parser.add_argument(
        "--save-iteration",
        action="store_true",
        help="Save results to iteration log"
    )
    parser.add_argument(
        "--iteration-notes",
        type=str,
        default="",
        help="Notes to add to iteration log entry"
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

            if args.analyze_failures:
                metrics, image_results = await evaluate_corpus_detailed(
                    args.corpus,
                    use_llm=use_llm,
                    verbose=args.verbose,
                    max_images=args.max_images
                )
                failure_summary = analyze_failures(image_results)
            else:
                metrics = await evaluate_corpus(
                    args.corpus, use_llm=use_llm, verbose=args.verbose
                )
                image_results = []
                failure_summary = {}
        else:
            # Single image mode
            gt_path = find_ground_truth(args.image, args.image.parent)
            if not gt_path:
                print(f"No ground truth found for {args.image.name}")
                print(f"Run with --generate-stubs to create one")
                return

            ground_truth = load_ground_truth(gt_path)

            if args.analyze_failures:
                result = await evaluate_image_detailed(
                    args.image, ground_truth, use_llm=use_llm
                )
                metrics = AccuracyMetrics()
                metrics.true_positives = result.true_positives
                metrics.false_positives = result.false_positives
                metrics.false_negatives = result.false_negatives
                image_results = [result]
                failure_summary = analyze_failures(image_results)
            else:
                metrics = await evaluate_image(args.image, ground_truth, use_llm=use_llm)
                image_results = []
                failure_summary = {}

        # Check if targets are met
        targets_met, target_results = check_targets_met(metrics)

        # Output results
        if args.json:
            output = {
                "metrics": {
                    "precision": metrics.precision,
                    "recall": metrics.recall,
                    "f1": metrics.f1,
                    "true_positives": metrics.true_positives,
                    "false_positives": metrics.false_positives,
                    "false_negatives": metrics.false_negatives,
                    "rating_mae_db": metrics.rating_mae_db,
                    "rating_mae_llm": metrics.rating_mae_llm,
                    "wines_with_ratings_pct": metrics.wines_with_ratings_pct,
                },
                "targets": target_results,
                "targets_met": targets_met,
            }

            if args.analyze_failures:
                output["failure_analysis"] = failure_summary

            print(json.dumps(output, indent=2))
        else:
            print()
            print(metrics.summary())

            # Show pass/fail vs targets
            print()
            print("Target Comparison")
            print("-" * 40)

            for name, result in target_results.items():
                symbol = "OK" if result["met"] else "FAIL"
                print(f"[{symbol}] {name}: {result['value']:.3f} (target >= {result['target']})")

            if targets_met:
                print()
                print("ALL TARGETS MET!")
            else:
                print()
                print("Targets not met - continue iterating")

            # Show failure analysis
            if args.analyze_failures and failure_summary:
                print()
                print("Failure Analysis")
                print("-" * 40)
                counts = failure_summary.get("counts", {})
                total = failure_summary.get("total_failures", 0)

                if total > 0:
                    for category, count in sorted(counts.items(), key=lambda x: -x[1]):
                        if count > 0:
                            pct = count / total * 100
                            print(f"  {category}: {count} ({pct:.1f}%)")

                    # Show examples for top failure category
                    top_category = max(counts.items(), key=lambda x: x[1])[0]
                    examples = failure_summary.get("examples", {}).get(top_category, [])

                    if examples:
                        print()
                        print(f"Top failure examples ({top_category}):")
                        for ex in examples[:3]:
                            print(f"  - {ex['image']}: expected '{ex['expected']}'")
                            if ex.get('detected'):
                                print(f"    detected: '{ex['detected']}'")
                            if ex.get('ocr_text'):
                                print(f"    OCR: '{ex['ocr_text'][:50]}...'")

        # Save to iteration log if requested
        if args.save_iteration:
            log_path = args.corpus.parent / "iteration_log.json" if args.corpus else Path("iteration_log.json")
            log_data = load_iteration_log(log_path)

            iteration_num = len(log_data["iterations"]) + 1

            iteration_entry = {
                "iteration": iteration_num,
                "timestamp": datetime.now().isoformat(),
                "metrics": {
                    "precision": metrics.precision,
                    "recall": metrics.recall,
                    "f1": metrics.f1,
                    "true_positives": metrics.true_positives,
                    "false_positives": metrics.false_positives,
                    "false_negatives": metrics.false_negatives,
                },
                "targets_met": targets_met,
                "notes": args.iteration_notes,
            }

            if args.analyze_failures:
                iteration_entry["failure_summary"] = failure_summary.get("counts", {})

            log_data["iterations"].append(iteration_entry)
            save_iteration_log(log_path, log_data)
            print(f"\nSaved iteration {iteration_num} to {log_path}")

    asyncio.run(run())


if __name__ == "__main__":
    main()
