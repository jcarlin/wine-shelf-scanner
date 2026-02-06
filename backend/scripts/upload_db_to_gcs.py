#!/usr/bin/env python3
"""
Upload wines.db to GCS bucket (gzip-compressed).

Usage:
    python scripts/upload_db_to_gcs.py [--bucket BUCKET] [--path PATH] [--db-file DB]

Defaults:
    --bucket: GCS_DB_BUCKET env var (required)
    --path:   data/wines.db.gz
    --db-file: app/data/wines.db
"""

import argparse
import gzip
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent


def upload(db_file: str, bucket_name: str, gcs_path: str):
    """Gzip-compress and upload local DB file to GCS."""
    from google.cloud import storage

    db_path = Path(db_file)
    if not db_path.exists():
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)

    raw_size_mb = db_path.stat().st_size / (1024 * 1024)
    print(f"Compressing {db_path} ({raw_size_mb:.1f} MB)...")

    start = time.time()

    # Compress to a temp file
    with tempfile.NamedTemporaryFile(suffix=".gz", delete=False) as tmp:
        tmp_path = tmp.name
        with open(db_path, "rb") as f_in, gzip.open(tmp, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)

    gz_size_mb = Path(tmp_path).stat().st_size / (1024 * 1024)
    compress_time = time.time() - start
    ratio = (1 - gz_size_mb / raw_size_mb) * 100
    print(f"Compressed to {gz_size_mb:.1f} MB ({ratio:.0f}% reduction) in {compress_time:.1f}s")
    print(f"Uploading -> gs://{bucket_name}/{gcs_path}")

    try:
        upload_start = time.time()
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_path)

        blob.upload_from_filename(tmp_path, timeout=600)

        upload_time = time.time() - upload_start
        total_time = time.time() - start
        print(f"Upload complete in {upload_time:.1f}s ({gz_size_mb / upload_time:.1f} MB/s)")
        print(f"Total time: {total_time:.1f}s")
    finally:
        os.unlink(tmp_path)


def main():
    parser = argparse.ArgumentParser(description="Upload wines.db to GCS (gzip)")
    parser.add_argument(
        "--bucket",
        default=os.getenv("GCS_DB_BUCKET", ""),
        help="GCS bucket name (default: GCS_DB_BUCKET env var)",
    )
    parser.add_argument(
        "--path",
        default="data/wines.db.gz",
        help="GCS object path (default: data/wines.db.gz)",
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
