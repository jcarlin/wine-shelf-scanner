#!/usr/bin/env python3
"""
Wine Coverage Analysis CLI

Analyzes which wines are being requested but not found in the database.
Uses the LLM ratings cache to identify gaps in coverage.

Usage:
    python scripts/coverage_analysis.py
    python scripts/coverage_analysis.py --min-hits 3
    python scripts/coverage_analysis.py --export coverage_gaps.csv
"""

import argparse
import csv
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.llm_rating_cache import get_llm_rating_cache


def main():
    parser = argparse.ArgumentParser(
        description="Wine Coverage Analysis - Find missing wines",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/coverage_analysis.py
    python scripts/coverage_analysis.py --min-hits 3
    python scripts/coverage_analysis.py --export coverage_gaps.csv
    python scripts/coverage_analysis.py --top 20
        """
    )

    parser.add_argument(
        "--min-hits",
        type=int,
        default=1,
        help="Minimum request count to include (default: 1)"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=50,
        help="Show top N wines by request count (default: 50)"
    )
    parser.add_argument(
        "--export",
        type=Path,
        help="Export results to CSV file"
    )
    parser.add_argument(
        "--promotion-only",
        action="store_true",
        help="Only show wines eligible for promotion (5+ hits)"
    )

    args = parser.parse_args()

    cache = get_llm_rating_cache()
    stats = cache.get_stats()

    print("Wine Coverage Analysis")
    print("=" * 60)
    print()
    print(f"LLM Ratings Cache Statistics:")
    print(f"  Total cached wines:      {stats['total_entries']}")
    print(f"  Total requests served:   {stats['total_hits']}")
    print(f"  Promotion candidates:    {stats['promotion_candidates']} (5+ hits)")
    print()

    # Get candidates based on args
    if args.promotion_only:
        candidates = cache.get_promotion_candidates(min_hits=5)
        title = "Promotion Candidates (5+ requests)"
    else:
        candidates = cache.get_promotion_candidates(min_hits=args.min_hits)
        title = f"Missing Wines ({args.min_hits}+ requests)"

    if not candidates:
        print(f"No wines found with {args.min_hits}+ requests.")
        print("The cache builds up as users scan wine shelves.")
        return

    # Limit to top N
    candidates = candidates[:args.top]

    print(f"{title}:")
    print("-" * 60)
    print(f"{'Wine Name':<40} {'Hits':>6} {'Rating':>6} {'Provider':>10}")
    print("-" * 60)

    for c in candidates:
        name_display = c.wine_name[:37] + "..." if len(c.wine_name) > 40 else c.wine_name
        print(f"{name_display:<40} {c.hit_count:>6} {c.estimated_rating:>6.1f} {c.llm_provider:>10}")

    print("-" * 60)
    print(f"Showing {len(candidates)} wines")

    # Export if requested
    if args.export:
        with open(args.export, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "wine_name",
                "hit_count",
                "estimated_rating",
                "confidence",
                "llm_provider",
                "created_at",
                "last_accessed_at"
            ])
            for c in candidates:
                writer.writerow([
                    c.wine_name,
                    c.hit_count,
                    c.estimated_rating,
                    c.confidence,
                    c.llm_provider,
                    c.created_at.isoformat(),
                    c.last_accessed_at.isoformat()
                ])
        print(f"\nExported to {args.export}")

    # Recommendations
    print()
    print("Recommendations:")
    print("-" * 60)

    if stats['promotion_candidates'] > 0:
        print(f"  • {stats['promotion_candidates']} wines should be added to the database")
        print("    Run: python scripts/promote_cached_ratings.py")
    else:
        print("  • No wines have enough requests for promotion yet")

    llm_pct = (stats['total_entries'] / max(stats['total_entries'] + 1, 1)) * 100
    print(f"  • {stats['total_entries']} unique wines served by LLM")
    print(f"  • Consider adding popular wine datasets to reduce LLM reliance")


if __name__ == "__main__":
    main()
