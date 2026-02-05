#!/usr/bin/env python3
"""
Upload wines.db to GCS bucket.

Usage:
    python scripts/upload_db_to_gcs.py [--bucket BUCKET] [--path PATH] [--db-file DB]

Defaults:
    --bucket: GCS_DB_BUCKET env var (required)
    --path:   data/wines.db
    --db-file: app/data/wines.db
"""

import argparse
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent


def upload(db_file: str, bucket_name: str, gcs_path: str):
    """Upload local DB file to GCS."""
    from google.cloud import storage

    db_path = Path(db_file)
    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)

    size_mb = db_path.stat().st_size / (1024 * 1024)
    print(f"Uploading {db_path} ({size_mb:.1f} MB)")
    print(f"  -> gs://{bucket_name}/{gcs_path}")

    start = time.time()
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)

    # Resumable upload for large files
    blob.upload_from_filename(str(db_path), timeout=600)

    elapsed = time.time() - start
    print(f"Upload complete in {elapsed:.1f}s ({size_mb / elapsed:.1f} MB/s)")


def main():
    parser = argparse.ArgumentParser(description="Upload wines.db to GCS")
    parser.add_argument(
        "--bucket",
        default=os.getenv("GCS_DB_BUCKET", ""),
        help="GCS bucket name (default: GCS_DB_BUCKET env var)",
    )
    parser.add_argument(
        "--path",
        default="data/wines.db",
        help="GCS object path (default: data/wines.db)",
    )
    parser.add_argument(
        "--db-file",
        default=str(BACKEND_DIR / "app" / "data" / "wines.db"),
        help="Local database file path",
    )
    args = parser.parse_args()

    if not args.bucket:
        print("Error: No bucket specified. Set GCS_DB_BUCKET or use --bucket")
        sys.exit(1)

    upload(args.db_file, args.bucket, args.path)


if __name__ == "__main__":
    main()
