"""Add bug_reports table for user-submitted issue reports.

Revision ID: 002
Revises: 001
Create Date: 2026-02-05

Adds bug_reports table to store user reports from error screens,
partial detection toasts, and fallback lists in both iOS and Next.js.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    raw_conn = conn.connection.dbapi_connection

    raw_conn.executescript("""
        CREATE TABLE IF NOT EXISTS bug_reports (
            id TEXT PRIMARY KEY,
            report_type TEXT NOT NULL,
            error_type TEXT,
            error_message TEXT,
            user_description TEXT,
            image_id TEXT,
            device_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            app_version TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_bug_reports_type ON bug_reports(report_type);
        CREATE INDEX IF NOT EXISTS idx_bug_reports_platform ON bug_reports(platform);
        CREATE INDEX IF NOT EXISTS idx_bug_reports_created_at ON bug_reports(created_at);
    """)


def downgrade() -> None:
    conn = op.get_bind()
    raw_conn = conn.connection.dbapi_connection
    raw_conn.execute("DROP TABLE IF EXISTS bug_reports")
