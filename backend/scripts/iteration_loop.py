#!/usr/bin/env python3
"""
Iterative Accuracy Development Loop

Automates the cycle of:
1. Running accuracy tests
2. Analyzing failure patterns
3. Suggesting code improvements
4. Tracking progress

Usage:
    python scripts/iteration_loop.py --corpus ../test-images/corpus/labels/ --max-iterations 5
    python scripts/iteration_loop.py --status  # Show current iteration status
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.accuracy_report import (
    evaluate_corpus_detailed,
    analyze_failures,
    check_targets_met,
    load_iteration_log,
    save_iteration_log,
    FailureCategory,
)


# Success targets
TARGETS = {
    "precision": 0.85,
    "recall": 0.80,
    "f1": 0.82,
}


@dataclass
class IterationSuggestion:
    """A suggested improvement based on failure analysis."""
    category: str
    priority: int  # 1 = highest
    file_path: str
    description: str
    code_hint: Optional[str] = None


def generate_improvement_suggestions(failure_summary: dict) -> list[IterationSuggestion]:
    """
    Generate improvement suggestions based on failure analysis.

    Args:
        failure_summary: Output from analyze_failures()

    Returns:
        List of suggested improvements, sorted by priority
    """
    suggestions = []
    counts = failure_summary.get("counts", {})
    total = failure_summary.get("total_failures", 0)

    if total == 0:
        return []

    # OCR errors - text extraction failed
    ocr_errors = counts.get(FailureCategory.OCR_ERROR, 0)
    if ocr_errors > 0:
        pct = ocr_errors / total * 100
        suggestions.append(IterationSuggestion(
            category=FailureCategory.OCR_ERROR,
            priority=1 if pct > 30 else 2,
            file_path="app/services/ocr_processor.py",
            description=f"OCR errors: {ocr_errors} ({pct:.0f}%) - Text extraction failing",
            code_hint="""
Consider:
- Check PROXIMITY_THRESHOLD in config.py (currently 0.20)
- Improve text normalization patterns
- Check MIN_TEXT_LENGTH and MAX_TEXT_LENGTH filters
- Review text grouping logic in process() method
"""
        ))

    # Matching errors - right text, wrong match
    matching_errors = counts.get(FailureCategory.MATCHING_ERROR, 0)
    if matching_errors > 0:
        pct = matching_errors / total * 100
        suggestions.append(IterationSuggestion(
            category=FailureCategory.MATCHING_ERROR,
            priority=1 if pct > 30 else 2,
            file_path="app/services/wine_matcher.py",
            description=f"Matching errors: {matching_errors} ({pct:.0f}%) - Wrong wine matched",
            code_hint="""
Consider:
- Review FTS5 query construction
- Add more wine aliases for common variations
- Check if winery name should be part of match
- Consider fuzzy matching fallback for FTS misses
"""
        ))

    # Threshold too high - correct match filtered out
    threshold_high = counts.get(FailureCategory.THRESHOLD_HIGH, 0)
    if threshold_high > 0:
        pct = threshold_high / total * 100
        suggestions.append(IterationSuggestion(
            category=FailureCategory.THRESHOLD_HIGH,
            priority=1,
            file_path="app/config.py",
            description=f"Threshold too high: {threshold_high} ({pct:.0f}%) - Good matches filtered",
            code_hint="""
Consider lowering thresholds in config.py:
- VISIBILITY_THRESHOLD: 0.45 -> try 0.40
- TAPPABLE_THRESHOLD: 0.65 -> try 0.60
- FUZZY_CONFIDENCE_THRESHOLD: 0.7 -> try 0.65

Also check name_match_threshold in metrics.py (currently 0.8)
"""
        ))

    # Threshold too low - wrong match accepted
    threshold_low = counts.get(FailureCategory.THRESHOLD_LOW, 0)
    if threshold_low > 0:
        pct = threshold_low / total * 100
        suggestions.append(IterationSuggestion(
            category=FailureCategory.THRESHOLD_LOW,
            priority=1,
            file_path="app/config.py",
            description=f"Threshold too low: {threshold_low} ({pct:.0f}%) - Bad matches accepted",
            code_hint="""
Consider raising thresholds in config.py:
- MIN_SIMILARITY: 0.6 -> try 0.65
- FTS confidence of 0.85 may be too high for partial matches

Or improve matching specificity in wine_matcher.py
"""
        ))

    # Not in database - wine not found, LLM used
    not_in_db = counts.get(FailureCategory.NOT_IN_DB, 0)
    if not_in_db > 0:
        pct = not_in_db / total * 100
        suggestions.append(IterationSuggestion(
            category=FailureCategory.NOT_IN_DB,
            priority=2 if pct < 20 else 1,
            file_path="app/data/wines.db",
            description=f"Not in DB: {not_in_db} ({pct:.0f}%) - Wine not found in database",
            code_hint="""
Options:
- Add missing wines to database via ingestion pipeline
- Add aliases for alternate wine names
- Improve LLM fallback accuracy (if LLM is finding them)
- Check if wine names need normalization before lookup
"""
        ))

    # Unknown failures
    unknown = counts.get(FailureCategory.UNKNOWN, 0)
    if unknown > 0:
        pct = unknown / total * 100
        suggestions.append(IterationSuggestion(
            category=FailureCategory.UNKNOWN,
            priority=3,
            file_path="various",
            description=f"Unknown failures: {unknown} ({pct:.0f}%) - Need manual investigation",
            code_hint="""
Review the failure examples to understand root cause.
May need to add new failure categories or improve categorization.
"""
        ))

    # Sort by priority
    suggestions.sort(key=lambda s: s.priority)

    return suggestions


def print_iteration_summary(
    iteration: int,
    metrics: dict,
    targets_met: bool,
    failure_summary: dict,
    suggestions: list[IterationSuggestion]
) -> None:
    """Print a formatted summary of the iteration results."""
    print()
    print("=" * 60)
    print(f"ITERATION {iteration} SUMMARY")
    print("=" * 60)
    print()

    # Metrics
    print("Metrics:")
    print(f"  Precision: {metrics['precision']:.3f} (target >= {TARGETS['precision']})")
    print(f"  Recall:    {metrics['recall']:.3f} (target >= {TARGETS['recall']})")
    print(f"  F1 Score:  {metrics['f1']:.3f} (target >= {TARGETS['f1']})")
    print()

    # Status
    if targets_met:
        print("STATUS: ALL TARGETS MET!")
        return
    else:
        print("STATUS: Targets not met - improvements needed")

    # Failure breakdown
    if failure_summary:
        print()
        print("Failure Breakdown:")
        counts = failure_summary.get("counts", {})
        total = failure_summary.get("total_failures", 0)
        for category, count in sorted(counts.items(), key=lambda x: -x[1]):
            if count > 0:
                pct = count / total * 100
                print(f"  {category}: {count} ({pct:.0f}%)")

    # Suggestions
    if suggestions:
        print()
        print("Improvement Suggestions (by priority):")
        for i, sug in enumerate(suggestions[:5], 1):
            print(f"\n  {i}. [{sug.category}] Priority {sug.priority}")
            print(f"     File: {sug.file_path}")
            print(f"     Issue: {sug.description}")
            if sug.code_hint:
                print(f"     Hint: {sug.code_hint.strip().split(chr(10))[0]}")


def show_iteration_history(log_path: Path) -> None:
    """Display iteration history from log."""
    log_data = load_iteration_log(log_path)
    iterations = log_data.get("iterations", [])

    if not iterations:
        print("No iterations recorded yet.")
        return

    print()
    print("=" * 60)
    print("ITERATION HISTORY")
    print("=" * 60)
    print()
    print(f"{'Iter':<6} {'Timestamp':<20} {'Precision':<10} {'Recall':<10} {'F1':<10} {'Status':<10}")
    print("-" * 66)

    for it in iterations:
        m = it.get("metrics", {})
        status = "MET" if it.get("targets_met") else "..."
        ts = it.get("timestamp", "")[:16].replace("T", " ")
        print(f"{it.get('iteration', '?'):<6} {ts:<20} {m.get('precision', 0):<10.3f} {m.get('recall', 0):<10.3f} {m.get('f1', 0):<10.3f} {status:<10}")

    # Show trend
    if len(iterations) >= 2:
        first = iterations[0].get("metrics", {})
        last = iterations[-1].get("metrics", {})
        print()
        print("Progress:")
        for metric in ["precision", "recall", "f1"]:
            delta = last.get(metric, 0) - first.get(metric, 0)
            arrow = "+" if delta >= 0 else ""
            print(f"  {metric}: {arrow}{delta:.3f} ({first.get(metric, 0):.3f} -> {last.get(metric, 0):.3f})")


async def run_iteration(
    corpus_dir: Path,
    use_llm: bool = True,
    max_images: Optional[int] = None,
    save_to_log: bool = True,
    notes: str = ""
) -> tuple[bool, dict]:
    """
    Run a single iteration of the accuracy improvement loop.

    Args:
        corpus_dir: Path to corpus directory
        use_llm: Whether to use LLM fallback
        max_images: Limit number of images
        save_to_log: Whether to save results to iteration log
        notes: Notes to add to log entry

    Returns:
        Tuple of (targets_met, metrics_dict)
    """
    # Run evaluation with failure analysis
    print(f"Running evaluation on {corpus_dir}...")
    metrics, image_results = await evaluate_corpus_detailed(
        corpus_dir,
        use_llm=use_llm,
        verbose=False,
        max_images=max_images
    )

    # Analyze failures
    failure_summary = analyze_failures(image_results)

    # Check targets
    targets_met, target_results = check_targets_met(metrics)

    # Generate suggestions
    suggestions = generate_improvement_suggestions(failure_summary)

    # Get or create iteration number
    log_path = corpus_dir.parent / "iteration_log.json"
    log_data = load_iteration_log(log_path)
    iteration_num = len(log_data.get("iterations", [])) + 1

    # Build metrics dict
    metrics_dict = {
        "precision": metrics.precision,
        "recall": metrics.recall,
        "f1": metrics.f1,
        "true_positives": metrics.true_positives,
        "false_positives": metrics.false_positives,
        "false_negatives": metrics.false_negatives,
    }

    # Print summary
    print_iteration_summary(
        iteration_num,
        metrics_dict,
        targets_met,
        failure_summary,
        suggestions
    )

    # Save to log
    if save_to_log:
        iteration_entry = {
            "iteration": iteration_num,
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics_dict,
            "targets_met": targets_met,
            "failure_summary": failure_summary.get("counts", {}),
            "notes": notes,
        }

        log_data["iterations"].append(iteration_entry)
        save_iteration_log(log_path, log_data)
        print(f"\nSaved iteration {iteration_num} to {log_path}")

    return targets_met, metrics_dict


async def run_iteration_loop(
    corpus_dir: Path,
    max_iterations: int = 10,
    use_llm: bool = True,
    max_images: Optional[int] = None
) -> None:
    """
    Run the full iteration loop until targets are met or max iterations reached.

    Note: This is primarily for automated testing. For actual improvements,
    you'll need to make code changes between iterations.
    """
    print()
    print("=" * 60)
    print("STARTING ITERATION LOOP")
    print("=" * 60)
    print(f"Corpus: {corpus_dir}")
    print(f"Max iterations: {max_iterations}")
    print(f"Targets: Precision >= {TARGETS['precision']}, Recall >= {TARGETS['recall']}, F1 >= {TARGETS['f1']}")
    print()

    for i in range(max_iterations):
        print()
        print(f"--- Running iteration {i + 1} of {max_iterations} ---")

        targets_met, metrics = await run_iteration(
            corpus_dir,
            use_llm=use_llm,
            max_images=max_images,
            save_to_log=True,
            notes=f"Automated iteration {i + 1}"
        )

        if targets_met:
            print()
            print("=" * 60)
            print("SUCCESS! All targets met.")
            print("=" * 60)
            return

        print()
        print("Targets not met. Make improvements before next iteration.")
        print("Use --status to see history and suggestions.")
        return  # Exit after one iteration - manual improvements needed

    print()
    print(f"Max iterations ({max_iterations}) reached without meeting targets.")


def main():
    parser = argparse.ArgumentParser(
        description="Iterative Accuracy Development Loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run a single iteration with analysis
    python scripts/iteration_loop.py --corpus ../test-images/corpus/labels/

    # Run with quick test (10 images)
    python scripts/iteration_loop.py --corpus ../test-images/corpus/labels/ --max-images 10

    # Show iteration history
    python scripts/iteration_loop.py --status --corpus ../test-images/corpus/labels/

    # Run multiple iterations (automated mode)
    python scripts/iteration_loop.py --corpus ../test-images/corpus/labels/ --max-iterations 5
        """
    )

    parser.add_argument(
        "--corpus",
        type=Path,
        required=True,
        help="Path to corpus directory with images"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show iteration history instead of running"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=1,
        help="Maximum iterations to run (default: 1)"
    )
    parser.add_argument(
        "--max-images",
        type=int,
        help="Limit number of images per iteration"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM fallback"
    )
    parser.add_argument(
        "--notes",
        type=str,
        default="",
        help="Notes to add to iteration log"
    )

    args = parser.parse_args()

    if args.status:
        log_path = args.corpus.parent / "iteration_log.json"
        show_iteration_history(log_path)
        return

    use_llm = not args.no_llm

    if args.max_iterations > 1:
        asyncio.run(run_iteration_loop(
            args.corpus,
            max_iterations=args.max_iterations,
            use_llm=use_llm,
            max_images=args.max_images
        ))
    else:
        asyncio.run(run_iteration(
            args.corpus,
            use_llm=use_llm,
            max_images=args.max_images,
            save_to_log=True,
            notes=args.notes
        ))


if __name__ == "__main__":
    main()
