#!/usr/bin/env python3
"""
Wine data ingestion CLI tool.

Usage:
    python scripts/ingest.py --source kaggle     # Ingest Kaggle dataset
    python scripts/ingest.py --source vivino     # Ingest Vivino data (if available)
    python scripts/ingest.py --all               # Ingest all sources
    python scripts/ingest.py --stats             # Show database statistics
    python scripts/ingest.py --preview kaggle    # Preview first 10 records
    python scripts/ingest.py --clear             # Clear database and start fresh
"""

import argparse
import sys
import time
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.services.wine_repository import WineRepository
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.adapters.config_adapter import ConfigDrivenCSVAdapter


# Available data sources and their configs
SOURCES = {
    "kaggle": "app/ingestion/adapters/configs/kaggle_reviews.yaml",
    "kaggle130k": "app/ingestion/adapters/configs/kaggle_130k.yaml",
    "xwines": "xwines",  # Special handling - slim version
    "xwines_full": "xwines_full",  # Special handling - 100K wines + 21M ratings
    "vivino_brazil": "app/ingestion/adapters/configs/vivino_brazil.yaml",
    "vivino_global": "vivino_global",  # Special handling - multi-file scraped data
    "vivino_es": "app/ingestion/adapters/configs/vivino_es.yaml",
    "vivino_webscraper": "app/ingestion/adapters/configs/vivino_webscraper.yaml",
}


def validate_source_files(source_name: str) -> list[str]:
    """
    Validate that required files exist for a data source.

    Returns list of missing file paths (empty if all exist).
    """
    missing = []

    if source_name == "xwines":
        wines_path = backend_path / "../raw-data/archive/XWines_Slim_1K_wines.csv"
        ratings_path = backend_path / "../raw-data/archive/XWines_Slim_150K_ratings.csv"
        if not wines_path.exists():
            missing.append(str(wines_path))
        if not ratings_path.exists():
            missing.append(str(ratings_path))

    elif source_name == "xwines_full":
        wines_path = backend_path / "../raw-data/xwines_full_drive/last/XWines_Full_100K_wines.csv"
        ratings_path = backend_path / "../raw-data/xwines_full_drive/last/XWines_Full_21M_ratings.csv"
        if not wines_path.exists():
            missing.append(str(wines_path))
        if not ratings_path.exists():
            missing.append(str(ratings_path))

    elif source_name == "vivino_global":
        data_dir = backend_path / "../raw-data/vivino-scraped"
        if not data_dir.exists():
            missing.append(str(data_dir))

    elif source_name in SOURCES:
        config_path = backend_path / SOURCES[source_name]
        if not config_path.exists():
            missing.append(str(config_path))

    return missing


def get_adapter(source_name: str):
    """Get adapter for a data source."""
    if source_name not in SOURCES:
        available = ", ".join(SOURCES.keys())
        raise ValueError(f"Unknown source: {source_name}. Available: {available}")

    # Validate files exist before creating adapter
    missing = validate_source_files(source_name)
    if missing:
        print(f"\nError: Required files not found for '{source_name}':")
        for path in missing:
            print(f"  - {path}")
        print("\nSee raw-data/README.md for instructions on downloading datasets.")
        raise FileNotFoundError(f"Missing data files for {source_name}")

    if source_name == "xwines":
        from app.ingestion.adapters.xwines_adapter import XWinesAdapter
        return XWinesAdapter(
            wines_path=str(backend_path / "../raw-data/archive/XWines_Slim_1K_wines.csv"),
            ratings_path=str(backend_path / "../raw-data/archive/XWines_Slim_150K_ratings.csv"),
            min_ratings=3,
        )

    if source_name == "xwines_full":
        from app.ingestion.adapters.xwines_adapter import XWinesAdapter
        return XWinesAdapter(
            wines_path=str(backend_path / "../raw-data/xwines_full_drive/last/XWines_Full_100K_wines.csv"),
            ratings_path=str(backend_path / "../raw-data/xwines_full_drive/last/XWines_Full_21M_ratings.csv"),
            min_ratings=5,  # Higher threshold for more reliable ratings
        )

    if source_name == "vivino_global":
        from app.ingestion.adapters.vivino_global_adapter import VivinoGlobalAdapter
        return VivinoGlobalAdapter(
            data_dir=str(backend_path / "../raw-data/vivino-scraped"),
            min_reviews=10,  # Filter out wines with few reviews
        )

    config_path = backend_path / SOURCES[source_name]
    return ConfigDrivenCSVAdapter(str(config_path), base_path=str(backend_path))


def ingest_source(source_name: str, skip_existing: bool = True) -> dict:
    """Ingest a single data source."""
    print(f"\n{'='*60}")
    print(f"Ingesting: {source_name}")
    print(f"{'='*60}")

    adapter = get_adapter(source_name)
    repo = WineRepository()
    pipeline = IngestionPipeline(repository=repo)

    start_time = time.time()
    stats = pipeline.ingest(adapter, skip_existing=skip_existing)
    elapsed = time.time() - start_time

    if stats.records_skipped == -1:
        print(f"Skipped: already ingested (same file hash)")
        return stats.to_dict()

    print(f"\nCompleted in {elapsed:.1f}s")
    print(f"  Records read: {stats.records_read:,}")
    print(f"  Records processed: {stats.records_processed:,}")
    print(f"  Unique wines added: {stats.records_added:,}")
    print(f"  Duplicates merged: {stats.records_merged:,}")
    print(f"  Skipped (DB exists): {stats.records_skipped:,}")

    if stats.errors:
        print(f"  Errors: {len(stats.errors)}")
        for err in stats.errors[:5]:
            print(f"    - {err}")
        if len(stats.errors) > 5:
            print(f"    ... and {len(stats.errors) - 5} more")

    repo.close()
    return stats.to_dict()


def show_stats():
    """Show database statistics."""
    print("\n" + "="*60)
    print("Wine Database Statistics")
    print("="*60)

    repo = WineRepository()
    conn = repo._get_connection()
    cursor = conn.cursor()

    # Total count
    print(f"\nTotal wines: {repo.count():,}")

    # Rating distribution
    print("\nRating distribution (normalized 1-5 scale):")
    cursor.execute('''
        SELECT
            CASE
                WHEN rating >= 4.5 THEN "4.5-5.0 (Excellent)"
                WHEN rating >= 4.0 THEN "4.0-4.5 (Outstanding)"
                WHEN rating >= 3.5 THEN "3.5-4.0 (Very Good)"
                WHEN rating >= 3.0 THEN "3.0-3.5 (Good)"
                ELSE "Below 3.0"
            END as tier,
            COUNT(*) as count
        FROM wines
        GROUP BY tier
        ORDER BY tier DESC
    ''')
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,}")

    # Top countries
    print("\nTop 10 countries:")
    cursor.execute('''
        SELECT country, COUNT(*) as count
        FROM wines
        WHERE country IS NOT NULL
        GROUP BY country
        ORDER BY count DESC
        LIMIT 10
    ''')
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,}")

    # Top varietals
    print("\nTop 10 varietals:")
    cursor.execute('''
        SELECT varietal, COUNT(*) as count
        FROM wines
        WHERE varietal IS NOT NULL
        GROUP BY varietal
        ORDER BY count DESC
        LIMIT 10
    ''')
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]:,}")

    # Ingestion history
    print("\nIngestion history:")
    cursor.execute('''
        SELECT source_name, records_processed, records_added, run_at
        FROM ingestion_log
        ORDER BY run_at DESC
        LIMIT 5
    ''')
    for row in cursor.fetchall():
        print(f"  {row[3]}: {row[0]} - {row[1]:,} processed, {row[2]:,} added")

    repo.close()


def preview_source(source_name: str, limit: int = 10):
    """Preview records from a data source."""
    print(f"\nPreview: {source_name} (first {limit} records)")
    print("="*60)

    adapter = get_adapter(source_name)
    pipeline = IngestionPipeline()
    records = pipeline.preview(adapter, limit=limit)

    for i, record in enumerate(records, 1):
        print(f"\n{i}. {record['wine_name']}")
        print(f"   Rating: {record['original_rating']} → {record['normalized_rating']} (normalized)")
        print(f"   Winery: {record.get('winery', 'N/A')}")
        print(f"   Region: {record.get('region', 'N/A')}, Country: {record.get('country', 'N/A')}")
        print(f"   Varietal: {record.get('varietal', 'N/A')}")


def clear_database():
    """Clear all data from database."""
    print("\nClearing database...")

    db_path = backend_path / "app" / "data" / "wines.db"
    if db_path.exists():
        db_path.unlink()
        print("Database cleared.")
    else:
        print("No database to clear.")


def benchmark_lookups():
    """Benchmark wine lookup performance."""
    print("\n" + "="*60)
    print("Lookup Performance Benchmark")
    print("="*60)

    from app.services.wine_matcher import WineMatcher
    import random

    # Test with SQLite backend
    matcher = WineMatcher(use_sqlite=True)
    print(f"Database size: {matcher.wine_count():,} wines")

    # Get some random wine names for testing
    all_wines = matcher.get_all_wines()
    if len(all_wines) < 100:
        print("Not enough wines for benchmark")
        return

    # Sample 100 random wines
    sample_wines = random.sample(all_wines, 100)
    test_queries = [w['canonical_name'] for w in sample_wines]

    # Benchmark
    times = []
    for query in test_queries:
        start = time.perf_counter()
        matcher.match(query)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    max_time = max(times)
    min_time = min(times)

    print(f"\nExact match queries (100 samples):")
    print(f"  Average: {avg_time:.2f}ms")
    print(f"  Min: {min_time:.2f}ms")
    print(f"  Max: {max_time:.2f}ms")

    # Test fuzzy queries
    fuzzy_queries = [q[:len(q)//2] for q in test_queries[:20]]
    fuzzy_times = []
    for query in fuzzy_queries:
        start = time.perf_counter()
        matcher.match(query)
        elapsed = (time.perf_counter() - start) * 1000
        fuzzy_times.append(elapsed)

    avg_fuzzy = sum(fuzzy_times) / len(fuzzy_times)
    print(f"\nFuzzy match queries (20 samples):")
    print(f"  Average: {avg_fuzzy:.2f}ms")

    if avg_time < 50 and avg_fuzzy < 50:
        print("\n✓ Performance target met (< 50ms)")
    else:
        print(f"\n✗ Performance target NOT met (target: < 50ms)")


def main():
    parser = argparse.ArgumentParser(
        description="Wine data ingestion CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--source", "-s",
        choices=list(SOURCES.keys()),
        help="Data source to ingest"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Ingest all available sources"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show database statistics"
    )
    parser.add_argument(
        "--preview", "-p",
        choices=list(SOURCES.keys()),
        help="Preview records from a source"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear database"
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run lookup performance benchmark"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force re-ingestion even if already done"
    )

    args = parser.parse_args()

    if args.clear:
        response = input("This will delete all wine data. Continue? [y/N]: ").strip().lower()
        if response == 'y':
            clear_database()
        else:
            print("Aborted.")
        return

    if args.preview:
        preview_source(args.preview)
        return

    if args.stats:
        show_stats()
        return

    if args.benchmark:
        benchmark_lookups()
        return

    if args.source:
        ingest_source(args.source, skip_existing=not args.force)
        show_stats()
        return

    if args.all:
        for source in SOURCES:
            ingest_source(source, skip_existing=not args.force)
        show_stats()
        return

    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
