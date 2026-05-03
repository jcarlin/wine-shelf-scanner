"""Add vintage column to llm_ratings_cache.

Revision ID: 007
Revises: 006
Create Date: 2026-05-02

Adds TEXT vintage column to round-trip wine year alongside cached LLM ratings.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    raw_conn = conn.connection.dbapi_connection

    cursor = raw_conn.execute("PRAGMA table_info(llm_ratings_cache)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if "vintage" not in existing_columns:
        raw_conn.execute("ALTER TABLE llm_ratings_cache ADD COLUMN vintage TEXT")


def downgrade() -> None:
    # SQLite doesn't support DROP COLUMN; columns remain but are harmless if unused.
    pass
