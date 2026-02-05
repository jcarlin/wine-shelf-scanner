"""Initial schema - SQLite database with FTS5.

Revision ID: 001
Revises: None
Create Date: 2026-02-04

Applies the complete schema from app/data/schema.sql.
Tables: wines, wine_aliases, wine_sources, ingestion_log,
wine_fts, llm_ratings_cache, corrections, wine_reviews.
"""
from typing import Sequence, Union
from pathlib import Path

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    schema_path = Path(__file__).parent.parent.parent / "app" / "data" / "schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    schema_sql = schema_path.read_text()

    # Use raw DBAPI connection for multi-statement SQL with triggers
    conn = op.get_bind()
    raw_conn = conn.connection.dbapi_connection
    raw_conn.executescript(schema_sql)


def downgrade() -> None:
    conn = op.get_bind()
    raw_conn = conn.connection.dbapi_connection

    # Drop triggers first
    triggers = [
        "wines_ai", "wines_ad", "wines_au",
        "wine_aliases_ai", "wine_aliases_ad",
    ]
    for trigger in triggers:
        raw_conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")

    # Drop tables in reverse dependency order
    tables = [
        "wine_reviews",
        "corrections",
        "llm_ratings_cache",
        "wine_fts",
        "ingestion_log",
        "wine_sources",
        "wine_aliases",
        "wines",
    ]
    for table in tables:
        raw_conn.execute(f"DROP TABLE IF EXISTS {table}")
