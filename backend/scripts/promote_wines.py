#!/usr/bin/env python3
"""
Wine Promotion CLI

Manages promotion of frequently-requested LLM-estimated wines to the main database.

Usage:
    python -m scripts.promote_wines --preview
    python -m scripts.promote_wines --promote "Caymus Cabernet Sauvignon"
    python -m scripts.promote_wines --reject "Generic Red Wine"
    python -m scripts.promote_wines --auto --min-hits 10
    python -m scripts.promote_wines --stats
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.wine_promoter import WinePromoter


def format_date(dt) -> str:
    """Format datetime for display."""
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M")


def print_candidate(candidate, index: int = None) -> None:
    """Print a single candidate in a readable format."""
    prefix = f"{index}. " if index is not None else ""

    print(f"{prefix}{candidate.wine_name}")
    print(f"   Rating: {candidate.estimated_rating:.1f}  |  Hits: {candidate.hit_count}  |  Confidence: {candidate.confidence:.2f}")

    # Build metadata line
    metadata_parts = []
    if candidate.wine_type:
        metadata_parts.append(f"Type: {candidate.wine_type}")
    if candidate.varietal:
        metadata_parts.append(f"Varietal: {candidate.varietal}")
    if candidate.region:
        metadata_parts.append(f"Region: {candidate.region}")
    if candidate.brand:
        metadata_parts.append(f"Producer: {candidate.brand}")

    if metadata_parts:
        print(f"   {' | '.join(metadata_parts)}")

    print(f"   First seen: {format_date(candidate.created_at)}  |  Last seen: {format_date(candidate.last_accessed_at)}")
    print()


def cmd_preview(promoter: WinePromoter, min_hits: int) -> None:
    """Preview all promotion candidates."""
    candidates = promoter.get_candidates(min_hits=min_hits)

    if not candidates:
        print(f"No candidates found with >= {min_hits} hits.")
        return

    print(f"Promotion Candidates (min {min_hits} hits)")
    print("=" * 60)
    print()

    for i, candidate in enumerate(candidates, 1):
        print_candidate(candidate, index=i)

    print("-" * 60)
    print(f"Total candidates: {len(candidates)}")


def cmd_promote(promoter: WinePromoter, wine_name: str) -> bool:
    """Promote a specific wine to the main database."""
    print(f"Promoting: {wine_name}")

    success = promoter.promote(wine_name)

    if success:
        print(f"Successfully promoted '{wine_name}' to the main database.")
        return True
    else:
        print(f"Failed to promote '{wine_name}'. Wine may not exist in cache.")
        return False


def cmd_reject(promoter: WinePromoter, wine_name: str) -> bool:
    """Reject and remove a wine from the cache."""
    print(f"Rejecting: {wine_name}")

    success = promoter.reject(wine_name)

    if success:
        print(f"Successfully rejected and removed '{wine_name}' from cache.")
        return True
    else:
        print(f"Failed to reject '{wine_name}'. Wine may not exist in cache.")
        return False


def cmd_auto(promoter: WinePromoter, min_hits: int) -> int:
    """Auto-promote all wines meeting the threshold."""
    candidates = promoter.get_candidates(min_hits=min_hits)

    if not candidates:
        print(f"No candidates found with >= {min_hits} hits.")
        return 0

    print(f"Auto-promoting {len(candidates)} wines with >= {min_hits} hits")
    print("=" * 60)
    print()

    promoted_count = 0
    failed_count = 0

    for candidate in candidates:
        success = promoter.promote(candidate.wine_name)
        if success:
            print(f"  [OK] {candidate.wine_name} (rating: {candidate.estimated_rating:.1f}, hits: {candidate.hit_count})")
            promoted_count += 1
        else:
            print(f"  [FAIL] {candidate.wine_name}")
            failed_count += 1

    print()
    print("-" * 60)
    print(f"Promoted: {promoted_count}  |  Failed: {failed_count}")

    return promoted_count


def cmd_stats(promoter: WinePromoter) -> None:
    """Show cache statistics."""
    stats = promoter.get_stats()

    print("LLM Rating Cache Statistics")
    print("=" * 40)
    print(f"Total entries:         {stats.get('total_entries', 0):,}")
    print(f"Total hits:            {stats.get('total_hits', 0):,}")
    print(f"Promotion candidates:  {stats.get('promotion_candidates', 0):,}")

    # Calculate hit ratio if we have data
    total_entries = stats.get('total_entries', 0)
    total_hits = stats.get('total_hits', 0)
    if total_entries > 0:
        avg_hits = total_hits / total_entries
        print(f"Average hits/entry:    {avg_hits:.1f}")


def main():
    parser = argparse.ArgumentParser(
        description="Manage wine promotion from LLM cache to main database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Preview candidates with default threshold (5 hits)
    python -m scripts.promote_wines --preview

    # Preview with higher threshold
    python -m scripts.promote_wines --preview --min-hits 10

    # Promote a specific wine
    python -m scripts.promote_wines --promote "Caymus Cabernet Sauvignon"

    # Reject a bad candidate
    python -m scripts.promote_wines --reject "Generic Red Wine"

    # Auto-promote high-hit wines
    python -m scripts.promote_wines --auto --min-hits 10

    # Show cache statistics
    python -m scripts.promote_wines --stats
        """
    )

    # Action arguments (mutually exclusive)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--preview", "-p",
        action="store_true",
        help="Show all promotion candidates with their metadata"
    )
    action_group.add_argument(
        "--promote",
        type=str,
        metavar="WINE_NAME",
        help="Promote a specific wine to the main database"
    )
    action_group.add_argument(
        "--reject",
        type=str,
        metavar="WINE_NAME",
        help="Reject and remove a wine from the cache"
    )
    action_group.add_argument(
        "--auto",
        action="store_true",
        help="Auto-promote all wines meeting the threshold"
    )
    action_group.add_argument(
        "--stats",
        action="store_true",
        help="Show cache statistics"
    )

    # Options
    parser.add_argument(
        "--min-hits", "-m",
        type=int,
        default=5,
        help="Minimum hit count for preview/auto (default: 5)"
    )

    args = parser.parse_args()

    # Initialize promoter
    promoter = WinePromoter()

    # Execute command
    if args.preview:
        cmd_preview(promoter, min_hits=args.min_hits)
    elif args.promote:
        success = cmd_promote(promoter, wine_name=args.promote)
        sys.exit(0 if success else 1)
    elif args.reject:
        success = cmd_reject(promoter, wine_name=args.reject)
        sys.exit(0 if success else 1)
    elif args.auto:
        count = cmd_auto(promoter, min_hits=args.min_hits)
        sys.exit(0 if count > 0 else 1)
    elif args.stats:
        cmd_stats(promoter)


if __name__ == "__main__":
    main()
