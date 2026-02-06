"""Add review_text column to wine_reviews table.

Revision ID: 005
Revises: 004
Create Date: 2026-02-06

Adds a TEXT review_text column for tasting notes (nullable).
Adds partial index for fast text-review queries.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    raw_conn = conn.connection.dbapi_connection

    # Check if column already exists (idempotent)
    cursor = raw_conn.execute("PRAGMA table_info(wine_reviews)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if "review_text" not in existing_columns:
        raw_conn.execute("ALTER TABLE wine_reviews ADD COLUMN review_text TEXT")

    # Partial index for fast text-review queries
    raw_conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_wine_reviews_has_text
        ON wine_reviews(wine_id) WHERE review_text IS NOT NULL
    """)


def downgrade() -> None:
    # SQLite doesn't support DROP COLUMN; column remains but is harmless if unused.
    conn = op.get_bind()
    raw_conn = conn.connection.dbapi_connection
    raw_conn.execute("DROP INDEX IF EXISTS idx_wine_reviews_has_text")
