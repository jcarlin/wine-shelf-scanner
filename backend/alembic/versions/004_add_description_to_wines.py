"""Add description column to wines table.

Revision ID: 004
Revises: 003
Create Date: 2026-02-05

Adds a TEXT description column for tasting notes / review snippets.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    raw_conn = conn.connection.dbapi_connection

    # Check if column already exists (idempotent)
    cursor = raw_conn.execute("PRAGMA table_info(wines)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if "description" not in existing_columns:
        raw_conn.execute("ALTER TABLE wines ADD COLUMN description TEXT")


def downgrade() -> None:
    # SQLite doesn't support DROP COLUMN; column remains but is harmless if unused.
    pass
