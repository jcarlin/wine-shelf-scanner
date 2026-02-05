"""
/report endpoint for Wine Shelf Scanner.

Receives bug reports from users when errors, partial detection, or
full failure occur during scanning.
"""

import logging
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


# === Models ===


class ReportMetadata(BaseModel):
    """Optional metadata attached to a bug report."""
    wines_detected: Optional[int] = None
    wines_in_fallback: Optional[int] = None
    confidence_scores: Optional[list[float]] = None
    debug_data: Optional[dict] = None


class ReportRequest(BaseModel):
    """User bug report submission."""
    report_type: str = Field(
        ...,
        description="Type of report: error, partial_detection, full_failure, wrong_wine"
    )
    error_type: Optional[str] = Field(
        None,
        description="Error category: NETWORK_ERROR, SERVER_ERROR, TIMEOUT, PARSE_ERROR"
    )
    error_message: Optional[str] = Field(None, description="Error message shown to user")
    user_description: Optional[str] = Field(
        None,
        description="Optional user-provided description (max 500 chars)",
        max_length=500,
    )
    image_id: Optional[str] = Field(None, description="Image ID from scan response")
    device_id: str = Field(..., description="Anonymous device identifier")
    platform: str = Field(..., description="Client platform: ios, web, expo")
    app_version: Optional[str] = Field(None, description="Client app version")
    timestamp: Optional[str] = Field(None, description="ISO 8601 timestamp from client")
    metadata: Optional[ReportMetadata] = None


class ReportResponse(BaseModel):
    """Response after storing a bug report."""
    success: bool
    report_id: str


class ReportStats(BaseModel):
    """Aggregated bug report statistics."""
    total_reports: int
    by_type: dict[str, int]
    by_platform: dict[str, int]


# === Repository ===


class ReportRepository:
    """Thread-safe SQLite repository for bug reports."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "wines.db"
        self.db_path = str(db_path)
        self._local = threading.local()
        self._ensure_table()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
        return self._local.connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Cursor]:
        """Context manager for transactions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _ensure_table(self):
        """Ensure bug_reports table exists."""
        conn = self._get_connection()
        conn.execute("""
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
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bug_reports_type ON bug_reports(report_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bug_reports_platform ON bug_reports(platform)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bug_reports_created_at ON bug_reports(created_at)")
        conn.commit()

    def add_report(self, report: ReportRequest) -> str:
        """Store a bug report. Returns the report ID."""
        import json

        report_id = str(uuid.uuid4())
        metadata_json = None
        if report.metadata:
            metadata_json = json.dumps(report.metadata.model_dump(exclude_none=True))

        with self._transaction() as cursor:
            cursor.execute("""
                INSERT INTO bug_reports
                    (id, report_type, error_type, error_message, user_description,
                     image_id, device_id, platform, app_version, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report_id,
                report.report_type,
                report.error_type,
                report.error_message,
                report.user_description,
                report.image_id,
                report.device_id,
                report.platform,
                report.app_version,
                metadata_json,
            ))
        return report_id

    def get_stats(self) -> dict:
        """Get aggregated report statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM bug_reports")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT report_type, COUNT(*) FROM bug_reports GROUP BY report_type")
        by_type = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute("SELECT platform, COUNT(*) FROM bug_reports GROUP BY platform")
        by_platform = {row[0]: row[1] for row in cursor.fetchall()}

        return {
            "total_reports": total,
            "by_type": by_type,
            "by_platform": by_platform,
        }


# Singleton repository instance
_report_repo: Optional[ReportRepository] = None


def get_report_repo() -> ReportRepository:
    """Get or create report repository singleton."""
    global _report_repo
    if _report_repo is None:
        _report_repo = ReportRepository()
    return _report_repo


# === Endpoints ===


@router.post("/report", response_model=ReportResponse)
async def submit_report(report: ReportRequest) -> ReportResponse:
    """
    Submit a bug report.

    Use this endpoint when users report errors, partial detection issues,
    or full scan failures from the error/results screen.
    """
    try:
        repo = get_report_repo()
        report_id = repo.add_report(report)

        logger.info(
            f"Bug report received: type={report.report_type} "
            f"platform={report.platform} id={report_id}"
        )
        return ReportResponse(success=True, report_id=report_id)

    except Exception as e:
        logger.error(f"Error storing bug report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/report/stats", response_model=ReportStats)
async def get_report_stats() -> ReportStats:
    """
    Get aggregated bug report statistics.

    Returns total report count, breakdown by type and platform.
    """
    try:
        repo = get_report_repo()
        stats = repo.get_stats()
        return ReportStats(**stats)
    except Exception as e:
        logger.error(f"Error getting report stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
