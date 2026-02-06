"""
Backfill wine descriptions from Kaggle CSV into existing wines.db.

Reads tasting notes from the Kaggle datasets and updates wines that
already exist in the database (matched by canonical_name).

Usage:
    cd backend
    python -m scripts.backfill_descriptions [--dry-run] [--csv PATH]
"""

import argparse
import csv
import re
import sqlite3
import sys
from pathlib import Path

# Default CSV paths (relative to backend/)
DEFAULT_CSVS = [
    "../raw-data/winemag-data_first150k.csv",
    "../raw-data/winemag-data-130k-v2.csv",
]


def normalize_name(name: str) -> str:
    """Normalize wine name for matching (lowercase, no vintage, no extra spaces)."""
    name = name.lower()
    name = re.sub(r'\b(19|20)\d{2}\b', '', name)
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def build_wine_index(db_path: str) -> dict[str, int]:
    """Build normalized_name -> wine_id index from the database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT id, canonical_name FROM wines WHERE description IS NULL")
    index = {}
    for row in cursor.fetchall():
        key = normalize_name(row['canonical_name'])
        index[key] = row['id']

    conn.close()
    return index


def read_descriptions_from_csv(csv_path: str) -> dict[str, str]:
    """Read wine descriptions from a Kaggle CSV, keyed by normalized name."""
    descriptions = {}
    has_title = False

    with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        # Check if this CSV has a 'title' column
        if reader.fieldnames and 'title' in reader.fieldnames:
            has_title = True

        for row in reader:
            description = (row.get('description') or '').strip()
            if not description:
                continue

            # Build wine name the same way ingestion does
            if has_title and row.get('title'):
                # 130K dataset: use title directly
                wine_name = row['title'].strip()
                # Remove vintage prefix like ingestion does
                wine_name = re.sub(r'^\s*(19|20)\d{2}\s+', '', wine_name)
            else:
                # 150K dataset: winery+designation or winery+variety
                winery = (row.get('winery') or '').strip()
                designation = (row.get('designation') or '').strip()
                variety = (row.get('variety') or '').strip()

                if winery and designation:
                    wine_name = f"{winery} {designation}"
                elif winery and variety:
                    wine_name = f"{winery} {variety}"
                else:
                    continue

            key = normalize_name(wine_name)
            if key and key not in descriptions:
                descriptions[key] = description

    return descriptions


def backfill(db_path: str, csv_paths: list[str], dry_run: bool = False) -> tuple[int, int]:
    """
    Backfill descriptions into the database.

    Returns (updated_count, total_without_description).
    """
    # Build index of wines needing descriptions
    wine_index = build_wine_index(db_path)
    total_without = len(wine_index)
    print(f"Found {total_without} wines without descriptions in DB")

    # Collect descriptions from all CSVs
    all_descriptions: dict[str, str] = {}
    for csv_path in csv_paths:
        path = Path(csv_path)
        if not path.exists():
            print(f"  Skipping {csv_path} (not found)")
            continue
        descs = read_descriptions_from_csv(str(path))
        print(f"  Read {len(descs)} descriptions from {path.name}")
        # Don't overwrite — first CSV wins
        for key, desc in descs.items():
            if key not in all_descriptions:
                all_descriptions[key] = desc

    print(f"Total unique descriptions available: {len(all_descriptions)}")

    # Match and update
    updates = []
    for key, wine_id in wine_index.items():
        if key in all_descriptions:
            updates.append((all_descriptions[key], wine_id))

    print(f"Matched {len(updates)} wines for backfill")

    if dry_run:
        print("DRY RUN — no changes written")
        # Show a few examples
        for desc, wid in updates[:5]:
            print(f"  Wine ID {wid}: {desc[:80]}...")
        return len(updates), total_without

    # Write updates in batches
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    batch_size = 1000
    written = 0

    for i in range(0, len(updates), batch_size):
        batch = updates[i:i + batch_size]
        cursor.executemany(
            "UPDATE wines SET description = ? WHERE id = ?",
            batch
        )
        conn.commit()
        written += len(batch)
        if written % 10000 == 0:
            print(f"  Updated {written}/{len(updates)}...")

    conn.close()
    print(f"Updated {written} wines with descriptions")
    return written, total_without


def main():
    parser = argparse.ArgumentParser(description="Backfill wine descriptions from Kaggle CSV")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--csv", action="append", help="Path to CSV file (can specify multiple)")
    parser.add_argument("--db", default=None, help="Path to wines.db")
    args = parser.parse_args()

    # Resolve DB path
    if args.db:
        db_path = args.db
    else:
        # Default: backend/app/data/wines.db
        db_path = str(Path(__file__).parent.parent / "app" / "data" / "wines.db")

    if not Path(db_path).exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    # Resolve CSV paths
    csv_paths = args.csv if args.csv else [
        str(Path(__file__).parent.parent / p) for p in DEFAULT_CSVS
    ]

    updated, total = backfill(db_path, csv_paths, dry_run=args.dry_run)
    print(f"\nDone: {updated}/{total} wines updated with descriptions")


if __name__ == "__main__":
    main()
