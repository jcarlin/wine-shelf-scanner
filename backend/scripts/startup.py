#!/usr/bin/env python3
"""
Cloud Run startup script.

1. Download wines.db from GCS (if GCS_DB_BUCKET is set)
2. Run Alembic migrations (alembic upgrade head)
3. exec uvicorn to replace this process

For local development, skip GCS download and just run migrations + uvicorn.
"""

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - startup - %(levelname)s - %(message)s",
)
logger = logging.getLogger("startup")

# Resolve paths relative to backend/ directory
BACKEND_DIR = Path(__file__).parent.parent
DB_DIR = BACKEND_DIR / "app" / "data"


def download_db_from_gcs() -> bool:
    """Download wines.db from GCS bucket (supports gzip-compressed files).

    Returns True if download succeeded or was skipped.
    Returns False if download failed.
    """
    import gzip
    import shutil

    bucket = os.getenv("GCS_DB_BUCKET", "")
    gcs_path = os.getenv("GCS_DB_PATH", "data/wines.db.gz")
    db_path = os.getenv("DATABASE_PATH", str(DB_DIR / "wines.db"))

    if not bucket:
        logger.info("GCS_DB_BUCKET not set, skipping GCS download")
        return True

    # Ensure data directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # Skip if DB already exists (container restart / cached layer)
    if Path(db_path).exists():
        size_mb = Path(db_path).stat().st_size / (1024 * 1024)
        logger.info(
            f"Database already exists at {db_path} ({size_mb:.1f} MB), skipping download"
        )
        return True

    logger.info(f"Downloading gs://{bucket}/{gcs_path} -> {db_path}")
    start = time.time()

    try:
        from google.cloud import storage

        client = storage.Client()
        bucket_obj = client.bucket(bucket)
        blob = bucket_obj.blob(gcs_path)

        is_gz = gcs_path.endswith(".gz")

        if not blob.exists():
            if is_gz:
                # .gz not found, fall back to uncompressed
                fallback_path = gcs_path[:-3]
                logger.info(f"gz not found, trying uncompressed: {fallback_path}")
                blob = bucket_obj.blob(fallback_path)
                if not blob.exists():
                    logger.error(f"GCS object not found at {gcs_path} or {fallback_path}")
                    return False
            else:
                logger.error(f"GCS object gs://{bucket}/{gcs_path} does not exist")
                return False
            # Download uncompressed directly
            blob.download_to_filename(db_path)
            elapsed = time.time() - start
            size_mb = Path(db_path).stat().st_size / (1024 * 1024)
            logger.info(f"Downloaded {size_mb:.1f} MB in {elapsed:.1f}s (uncompressed)")
            return True

        if not is_gz:
            # Download uncompressed directly
            blob.download_to_filename(db_path)
            elapsed = time.time() - start
            size_mb = Path(db_path).stat().st_size / (1024 * 1024)
            logger.info(f"Downloaded {size_mb:.1f} MB in {elapsed:.1f}s")
            return True

        # Download gzip to temp file, then decompress
        gz_tmp = db_path + ".gz"
        blob.download_to_filename(gz_tmp)
        dl_time = time.time() - start
        gz_mb = Path(gz_tmp).stat().st_size / (1024 * 1024)
        logger.info(f"Downloaded {gz_mb:.1f} MB in {dl_time:.1f}s, decompressing...")

        with gzip.open(gz_tmp, "rb") as f_in, open(db_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

        os.unlink(gz_tmp)
        elapsed = time.time() - start
        size_mb = Path(db_path).stat().st_size / (1024 * 1024)
        logger.info(f"Decompressed to {size_mb:.1f} MB, total time {elapsed:.1f}s")
        return True

    except Exception as e:
        logger.error(f"Failed to download from GCS: {e}")
        return False


def run_migrations() -> bool:
    """Run Alembic migrations (upgrade head).

    Returns True on success, False on failure.
    """
    db_path = os.getenv("DATABASE_PATH", str(DB_DIR / "wines.db"))

    if not Path(db_path).exists():
        logger.info(f"No database at {db_path}, migrations will create schema")

    logger.info("Running alembic upgrade head...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(BACKEND_DIR),
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "DATABASE_PATH": db_path},
        )
        if result.returncode != 0:
            logger.error(f"Alembic migration failed:\n{result.stderr}")
            return False
        logger.info(f"Migrations complete: {result.stdout.strip()}")
        return True
    except subprocess.TimeoutExpired:
        logger.error("Alembic migration timed out after 120s")
        return False
    except Exception as e:
        logger.error(f"Migration error: {e}")
        return False


def exec_uvicorn():
    """Replace this process with uvicorn."""
    port = os.getenv("PORT", "8080")
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    logger.info(f"Starting uvicorn on port {port} (log_level={log_level})")

    os.execvp(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "0.0.0.0",
            "--port",
            port,
            "--log-level",
            log_level,
        ],
    )


def main():
    logger.info("=== Wine Scanner API Startup ===")

    # Step 1: Download DB from GCS
    if not download_db_from_gcs():
        logger.error("GCS download failed, exiting")
        sys.exit(1)

    # Step 2: Run migrations
    if not run_migrations():
        logger.warning(
            "Migration failed, continuing anyway (schema may already exist)"
        )

    # Step 3: Start uvicorn (replaces this process via execvp)
    exec_uvicorn()


if __name__ == "__main__":
    main()
