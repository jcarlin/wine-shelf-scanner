#!/bin/bash
# Unified database seed script.
#
# Rebuilds wines.db from scratch:
#   1. Delete existing DB
#   2. Run Alembic migrations (creates schema)
#   3. Ingest wine data from all sources
#   4. Ingest reviews (XWines 21M + Kaggle 280K)
#   5. Optionally upload to GCS
#
# Usage:
#   ./scripts/seed_db.sh                    # Full seed (wines + reviews)
#   ./scripts/seed_db.sh --wines-only       # Skip reviews ingestion
#   ./scripts/seed_db.sh --upload           # Upload to GCS after seeding
#   ./scripts/seed_db.sh --no-clear         # Don't delete existing DB first

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
DB_PATH="${DATABASE_PATH:-$BACKEND_DIR/app/data/wines.db}"

# Parse flags
WINES_ONLY=false
UPLOAD=false
NO_CLEAR=false

for arg in "$@"; do
    case $arg in
        --wines-only) WINES_ONLY=true ;;
        --upload)     UPLOAD=true ;;
        --no-clear)   NO_CLEAR=true ;;
        *)            echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

echo "========================================="
echo "Wine Database Seed Script"
echo "========================================="
echo "Database: $DB_PATH"
echo "Wines only: $WINES_ONLY"
echo "Upload to GCS: $UPLOAD"
echo ""

cd "$BACKEND_DIR"

# Step 1: Clear existing database
if [ "$NO_CLEAR" = false ]; then
    echo "Step 1: Deleting existing database..."
    rm -f "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm"
    echo "  Done."
else
    echo "Step 1: Skipped (--no-clear)"
fi
echo ""

# Step 2: Run migrations
echo "Step 2: Running Alembic migrations..."
python -m alembic upgrade head
echo "  Done."
echo ""

# Step 3: Ingest wines
echo "Step 3: Ingesting wine data..."
python -m scripts.ingest --all --force
echo "  Done."
echo ""

# Step 4: Ingest reviews (optional)
if [ "$WINES_ONLY" = false ]; then
    echo "Step 4: Ingesting reviews (this takes a while)..."
    python -m scripts.ingest_reviews
    echo "  Done."
else
    echo "Step 4: Skipped (--wines-only)"
fi
echo ""

# Step 5: Show stats
echo "Step 5: Database statistics"
python -m scripts.ingest --stats
echo ""

# Step 6: Upload to GCS (optional)
if [ "$UPLOAD" = true ]; then
    echo "Step 6: Uploading to GCS..."
    python scripts/upload_db_to_gcs.py --db-file "$DB_PATH"
    echo "  Done."
else
    echo "Step 6: Skipped (use --upload to upload to GCS)"
fi

echo ""
echo "========================================="
echo "Seed complete!"
echo "========================================="
