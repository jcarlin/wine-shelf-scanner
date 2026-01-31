#!/usr/bin/env python3
"""
Migrate ratings.json to SQLite database.

Usage:
    python scripts/migrate_json_to_sqlite.py

This creates/updates the wines.db file with data from ratings.json.
"""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.services.wine_repository import WineRepository


def main():
    """Run migration from ratings.json to SQLite."""
    data_dir = backend_path / "app" / "data"
    json_path = data_dir / "ratings.json"
    db_path = data_dir / "wines.db"

    if not json_path.exists():
        print(f"Error: ratings.json not found at {json_path}")
        sys.exit(1)

    print(f"Migrating from: {json_path}")
    print(f"Database path: {db_path}")

    # Create repository (initializes schema)
    repo = WineRepository(db_path=db_path)

    # Check if database already has data
    existing_count = repo.count()
    if existing_count > 0:
        print(f"Database already contains {existing_count} wines.")
        response = input("Clear and re-import? [y/N]: ").strip().lower()
        if response != 'y':
            print("Aborted.")
            sys.exit(0)

        # Clear existing data
        conn = repo._get_connection()
        conn.executescript("""
            DELETE FROM wine_sources;
            DELETE FROM wine_aliases;
            DELETE FROM wines;
            DELETE FROM wine_fts;
        """)
        conn.commit()
        print("Cleared existing data.")

    # Run migration
    migrated, skipped = repo.migrate_from_json(str(json_path))

    print(f"\nMigration complete:")
    print(f"  - Migrated: {migrated} wines")
    print(f"  - Skipped (duplicates): {skipped}")
    print(f"  - Total in database: {repo.count()}")

    # Verify a few wines
    print("\nVerification:")
    test_names = ["Opus One", "Caymus Cabernet Sauvignon", "Chateau Margaux"]
    for name in test_names:
        wine = repo.find_by_name(name)
        if wine:
            print(f"  ✓ Found: {wine.canonical_name} (rating: {wine.rating})")
        else:
            print(f"  ✗ Not found: {name}")

    repo.close()


if __name__ == "__main__":
    main()
