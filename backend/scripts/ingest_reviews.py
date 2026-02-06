#!/usr/bin/env python3
"""
Standalone script to ingest wine reviews into the wine_reviews table.

Sources:
  1. XWines Full 21M Ratings CSV (~21M rows, ratings only)
  2. Kaggle WineEnthusiast CSVs (~280K rows, with tasting notes)

Usage:
  cd backend && python -m scripts.ingest_reviews
  cd backend && python -m scripts.ingest_reviews --force   # re-ingest Kaggle with review_text
"""

import argparse
import csv
import os
import sqlite3
import sys
import time

# Paths relative to project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, "backend", "app", "data", "wines.db")
XWINES_RATINGS = os.path.join(PROJECT_ROOT, "raw-data", "xwines_full_drive", "last", "XWines_Full_21M_ratings.csv")
XWINES_WINES = os.path.join(PROJECT_ROOT, "raw-data", "xwines_full_drive", "last", "XWines_Full_100K_wines.csv")
KAGGLE_130K = os.path.join(PROJECT_ROOT, "raw-data", "winemag-data-130k-v2.csv")
KAGGLE_150K = os.path.join(PROJECT_ROOT, "raw-data", "winemag-data_first150k.csv")

BATCH_SIZE = 50_000
csv.field_size_limit(sys.maxsize)


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    return conn


def build_xwines_id_mapping(conn):
    """Build XWines WineID -> DB wine_id mapping via canonical_name."""
    print("Building XWines WineID -> wine_id mapping...")

    # Load DB canonical names into a lookup dict (lowercased for matching)
    cursor = conn.execute("SELECT id, canonical_name FROM wines")
    db_wines = {}
    for wine_id, name in cursor:
        db_wines[name.lower()] = wine_id
    print(f"  Loaded {len(db_wines)} wines from database")

    # Read XWines wines CSV to get WineID -> WineName
    mapping = {}  # XWines WineID (str) -> DB wine_id (int)
    matched = 0
    total = 0
    with open(XWINES_WINES, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            wine_name = row["WineName"].strip()
            xwines_id = row["WineID"]
            db_id = db_wines.get(wine_name.lower())
            if db_id is not None:
                mapping[xwines_id] = db_id
                matched += 1

    print(f"  Matched {matched}/{total} XWines wines to DB ({matched*100//total}%)")
    return mapping


def build_kaggle_name_mapping(conn):
    """Build a lookup from canonical_name (lowercased) -> wine_id for Kaggle matching."""
    cursor = conn.execute("SELECT id, canonical_name FROM wines")
    return {name.lower(): wine_id for wine_id, name in cursor}


def ingest_xwines_ratings(conn, xwines_mapping):
    """Stream and batch-insert XWines 21M ratings."""
    print(f"\n{'='*60}")
    print("Ingesting XWines ratings from:")
    print(f"  {XWINES_RATINGS}")

    if not os.path.exists(XWINES_RATINGS):
        print("  ERROR: File not found, skipping.")
        return 0

    # Check existing count for idempotency
    existing = conn.execute(
        "SELECT COUNT(*) FROM wine_reviews WHERE source_name = 'xwines'"
    ).fetchone()[0]
    if existing > 0:
        print(f"  Already have {existing:,} xwines reviews — skipping (idempotent).")
        return existing

    start = time.time()
    inserted = 0
    skipped_no_mapping = 0
    batch = []

    with open(XWINES_RATINGS, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            xwines_wine_id = row["WineID"]
            wine_id = xwines_mapping.get(xwines_wine_id)

            if wine_id is None:
                skipped_no_mapping += 1
                # Still insert with wine_id=NULL for completeness
                wine_id = None

            rating = float(row["Rating"])
            batch.append((
                wine_id,
                "xwines",
                row["UserID"],
                rating,
                row["Date"],
                row["Vintage"],
            ))

            if len(batch) >= BATCH_SIZE:
                conn.executemany(
                    """INSERT INTO wine_reviews (wine_id, source_name, user_id, rating, review_date, vintage)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    batch,
                )
                conn.commit()
                inserted += len(batch)
                batch = []

                if inserted % 1_000_000 == 0:
                    elapsed = time.time() - start
                    rate = inserted / elapsed
                    print(f"  Progress: {inserted:>12,} rows  ({elapsed:.0f}s, {rate:,.0f} rows/s)")

    # Final batch
    if batch:
        conn.executemany(
            """INSERT INTO wine_reviews (wine_id, source_name, user_id, rating, review_date, vintage)
               VALUES (?, ?, ?, ?, ?, ?)""",
            batch,
        )
        conn.commit()
        inserted += len(batch)

    elapsed = time.time() - start
    rate = inserted / elapsed if elapsed > 0 else 0
    print(f"  Completed: {inserted:,} rows inserted ({elapsed:.1f}s, {rate:,.0f} rows/s)")
    print(f"  Unmatched wine IDs (inserted with wine_id=NULL): {skipped_no_mapping:,}")
    return inserted


def ingest_kaggle_reviews(conn, name_mapping, force=False):
    """Ingest Kaggle WineEnthusiast reviews."""
    print(f"\n{'='*60}")
    print("Ingesting Kaggle WineEnthusiast reviews...")

    # Check existing count for idempotency
    existing = conn.execute(
        "SELECT COUNT(*) FROM wine_reviews WHERE source_name = 'kaggle_winemag'"
    ).fetchone()[0]
    if existing > 0:
        if force:
            print(f"  --force: Deleting {existing:,} existing kaggle_winemag rows...")
            conn.execute("DELETE FROM wine_reviews WHERE source_name = 'kaggle_winemag'")
            conn.commit()
        else:
            print(f"  Already have {existing:,} kaggle_winemag reviews — skipping (use --force to re-ingest).")
            return existing

    total_inserted = 0

    # Process the 130K file (has title + description columns)
    if os.path.exists(KAGGLE_130K):
        count = _ingest_kaggle_file(conn, KAGGLE_130K, name_mapping, has_title=True)
        total_inserted += count
        print(f"  {KAGGLE_130K}: {count:,} reviews")

    # Process the 150K file (no title, use winery + designation)
    if os.path.exists(KAGGLE_150K):
        count = _ingest_kaggle_file(conn, KAGGLE_150K, name_mapping, has_title=False)
        total_inserted += count
        print(f"  {KAGGLE_150K}: {count:,} reviews")

    conn.commit()
    print(f"  Total Kaggle reviews inserted: {total_inserted:,}")
    return total_inserted


def _ingest_kaggle_file(conn, filepath, name_mapping, has_title):
    """Ingest a single Kaggle WineEnthusiast CSV."""
    batch = []
    inserted = 0

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Build wine name for matching
            if has_title and "title" in row:
                wine_name = row["title"].strip()
            else:
                # Construct name from winery + designation
                winery = row.get("winery", "").strip()
                designation = row.get("designation", "").strip()
                variety = row.get("variety", "").strip()
                if designation:
                    wine_name = f"{winery} {designation}"
                else:
                    wine_name = f"{winery} {variety}"

            # Try to match to DB
            wine_id = name_mapping.get(wine_name.lower())

            # Convert points (80-100 scale) to 1-5 scale
            try:
                points = float(row["points"])
                rating = round((points - 80) / 4, 1)  # 80->0, 100->5
                rating = max(1.0, min(5.0, rating))
            except (ValueError, KeyError):
                continue

            user_id = row.get("taster_name", "").strip() or None

            # Extract review text (tasting notes) from description column
            review_text = row.get("description", "").strip() or None

            batch.append((
                wine_id,
                "kaggle_winemag",
                user_id,
                rating,
                None,  # no review_date
                None,  # no vintage in review context
                review_text,
            ))

            if len(batch) >= BATCH_SIZE:
                conn.executemany(
                    """INSERT INTO wine_reviews (wine_id, source_name, user_id, rating, review_date, vintage, review_text)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    batch,
                )
                inserted += len(batch)
                batch = []

    if batch:
        conn.executemany(
            """INSERT INTO wine_reviews (wine_id, source_name, user_id, rating, review_date, vintage, review_text)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            batch,
        )
        inserted += len(batch)

    return inserted


def main():
    parser = argparse.ArgumentParser(description="Ingest wine reviews into the database")
    parser.add_argument("--force", action="store_true",
                        help="Delete existing Kaggle reviews and re-ingest (with review_text)")
    args = parser.parse_args()

    print("Wine Reviews Ingestion Script")
    print(f"Database: {DB_PATH}")
    if args.force:
        print("Mode: --force (re-ingest Kaggle with review_text)")
    print()

    conn = get_db_connection()

    # Build mappings
    xwines_mapping = build_xwines_id_mapping(conn)
    name_mapping = build_kaggle_name_mapping(conn)

    # Ingest XWines ratings (21M)
    xwines_count = ingest_xwines_ratings(conn, xwines_mapping)

    # Ingest Kaggle reviews (~280K, with tasting notes)
    kaggle_count = ingest_kaggle_reviews(conn, name_mapping, force=args.force)

    # Final report
    total = conn.execute("SELECT COUNT(*) FROM wine_reviews").fetchone()[0]
    linked = conn.execute("SELECT COUNT(*) FROM wine_reviews WHERE wine_id IS NOT NULL").fetchone()[0]
    sources = conn.execute(
        "SELECT source_name, COUNT(*) FROM wine_reviews GROUP BY source_name"
    ).fetchall()

    print(f"\n{'='*60}")
    print("FINAL REPORT")
    print(f"{'='*60}")
    print(f"Total reviews in database: {total:,}")
    print(f"Linked to wines (wine_id NOT NULL): {linked:,}")
    print(f"Unlinked (wine_id NULL): {total - linked:,}")
    print("By source:")
    for source, count in sources:
        print(f"  {source}: {count:,}")

    conn.close()

    if total >= 1_000_000:
        print(f"\nSUCCESS: {total:,} reviews (target: 1,000,000)")
    else:
        print(f"\nWARNING: Only {total:,} reviews (target: 1,000,000)")


if __name__ == "__main__":
    main()
