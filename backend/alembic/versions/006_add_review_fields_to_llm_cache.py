"""Add blurb and review_snippets columns to llm_ratings_cache.

Revision ID: 006
Revises: 005
Create Date: 2026-02-06

Adds TEXT blurb column for 1-2 sentence wine description.
Adds TEXT review_snippets column for JSON-encoded tasting notes.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    raw_conn = conn.connection.dbapi_connection

    # Check if columns already exist (idempotent)
    cursor = raw_conn.execute("PRAGMA table_info(llm_ratings_cache)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if "blurb" not in existing_columns:
        raw_conn.execute("ALTER TABLE llm_ratings_cache ADD COLUMN blurb TEXT")

    if "review_snippets" not in existing_columns:
        raw_conn.execute("ALTER TABLE llm_ratings_cache ADD COLUMN review_snippets TEXT")


def downgrade() -> None:
    # SQLite doesn't support DROP COLUMN; columns remain but are harmless if unused.
    pass
