"""Add vision_cache table and backfill llm_ratings_cache columns.

Revision ID: 003
Revises: 002
Create Date: 2026-02-04

Creates vision_cache table for caching Vision API responses.
Also backfills missing columns in llm_ratings_cache for existing databases.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    raw_conn = conn.connection.dbapi_connection

    # Create vision_cache table
    raw_conn.executescript("""
        CREATE TABLE IF NOT EXISTS vision_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_hash TEXT NOT NULL UNIQUE,
            response_data BLOB NOT NULL,
            image_size_bytes INTEGER NOT NULL,
            response_size_bytes INTEGER NOT NULL,
            hit_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ttl_expires_at TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_vision_cache_hash
        ON vision_cache(image_hash);

        CREATE INDEX IF NOT EXISTS idx_vision_cache_expires
        ON vision_cache(ttl_expires_at);

        CREATE INDEX IF NOT EXISTS idx_vision_cache_lru
        ON vision_cache(last_accessed_at ASC);
    """)

    # Backfill missing columns in llm_ratings_cache
    # These columns exist in migration 001 but may be missing in databases
    # created before they were added to the inline schema.
    # SQLite doesn't support ADD COLUMN IF NOT EXISTS, so we check manually.
    cursor = raw_conn.execute("PRAGMA table_info(llm_ratings_cache)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    columns_to_add = [
        ("wine_type", "TEXT"),
        ("region", "TEXT"),
        ("varietal", "TEXT"),
        ("brand", "TEXT"),
    ]

    for col_name, col_type in columns_to_add:
        if col_name not in existing_columns:
            raw_conn.execute(
                f"ALTER TABLE llm_ratings_cache ADD COLUMN {col_name} {col_type}"
            )


def downgrade() -> None:
    conn = op.get_bind()
    raw_conn = conn.connection.dbapi_connection

    # Drop vision_cache table and indexes
    raw_conn.execute("DROP INDEX IF EXISTS idx_vision_cache_lru")
    raw_conn.execute("DROP INDEX IF EXISTS idx_vision_cache_expires")
    raw_conn.execute("DROP INDEX IF EXISTS idx_vision_cache_hash")
    raw_conn.execute("DROP TABLE IF EXISTS vision_cache")

    # Note: SQLite doesn't support DROP COLUMN, so we can't remove
    # the backfilled columns from llm_ratings_cache. They'll remain
    # but are harmless if unused.
