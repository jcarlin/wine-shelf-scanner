"""
/feedback endpoint for Wine Shelf Scanner.

Receives user feedback on wine match accuracy to enable self-improving system.
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


# === Models ===


class FeedbackRequest(BaseModel):
    """User feedback on a wine match."""
    image_id: str = Field(..., description="ID of the scan that produced this result")
    wine_name: str = Field(..., description="Wine name shown to user")
    is_correct: bool = Field(..., description="True if match was correct (thumbs up)")
    corrected_name: Optional[str] = Field(None, description="Correct wine name if is_correct=False")
    ocr_text: Optional[str] = Field(None, description="Original OCR text (for debugging)")
    device_id: Optional[str] = Field(None, description="Anonymous device identifier")


class FeedbackResponse(BaseModel):
    """Response after storing feedback."""
    success: bool
    message: str


class FeedbackStats(BaseModel):
    """Aggregated feedback statistics."""
    total_feedback: int
    correct_count: int
    incorrect_count: int
    correction_rate: float  # % marked incorrect


# === Repository ===


class FeedbackRepository:
    """Thread-safe SQLite repository for feedback/corrections."""

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
        """Ensure corrections table exists."""
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id TEXT NOT NULL,
                wine_name TEXT NOT NULL,
                ocr_text TEXT,
                is_correct BOOLEAN NOT NULL,
                corrected_name TEXT,
                device_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_corrections_wine_name ON corrections(LOWER(wine_name))")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_corrections_is_correct ON corrections(is_correct)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_corrections_created_at ON corrections(created_at)")
        conn.commit()

    def add_feedback(self, feedback: FeedbackRequest) -> bool:
        """Store user feedback. Returns True on success."""
        with self._transaction() as cursor:
            cursor.execute("""
                INSERT INTO corrections (image_id, wine_name, ocr_text, is_correct, corrected_name, device_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                feedback.image_id,
                feedback.wine_name,
                feedback.ocr_text,
                feedback.is_correct,
                feedback.corrected_name,
                feedback.device_id,
            ))
            return cursor.rowcount > 0

    def get_stats(self) -> dict:
        """Get aggregated feedback statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM corrections")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM corrections WHERE is_correct = 1")
        correct = cursor.fetchone()[0]

        incorrect = total - correct
        rate = (incorrect / total * 100) if total > 0 else 0.0

        return {
            "total_feedback": total,
            "correct_count": correct,
            "incorrect_count": incorrect,
            "correction_rate": round(rate, 2),
        }

    def get_corrections_for_wine(self, wine_name: str) -> list[dict]:
        """Get all corrections for a specific wine name."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM corrections
            WHERE LOWER(wine_name) = LOWER(?)
            ORDER BY created_at DESC
        """, (wine_name,))

        return [dict(row) for row in cursor.fetchall()]


# Singleton repository instance
_feedback_repo: Optional[FeedbackRepository] = None


def get_feedback_repo() -> FeedbackRepository:
    """Get or create feedback repository singleton."""
    global _feedback_repo
    if _feedback_repo is None:
        _feedback_repo = FeedbackRepository()
    return _feedback_repo


# === Endpoints ===


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(feedback: FeedbackRequest) -> FeedbackResponse:
    """
    Submit user feedback on a wine match.

    Use this endpoint when users indicate whether a wine match was correct
    (thumbs up) or incorrect (thumbs down with optional correction).
    """
    try:
        repo = get_feedback_repo()
        success = repo.add_feedback(feedback)

        if success:
            action = "confirmed" if feedback.is_correct else "corrected"
            logger.info(f"Feedback received: {feedback.wine_name} {action}")
            return FeedbackResponse(success=True, message="Feedback recorded")
        else:
            logger.warning(f"Failed to store feedback for {feedback.wine_name}")
            raise HTTPException(status_code=500, detail="Failed to store feedback")

    except Exception as e:
        logger.error(f"Error storing feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/feedback/stats", response_model=FeedbackStats)
async def get_feedback_stats() -> FeedbackStats:
    """
    Get aggregated feedback statistics.

    Returns total feedback count, correct/incorrect breakdown, and correction rate.
    Useful for monitoring system accuracy.
    """
    try:
        repo = get_feedback_repo()
        stats = repo.get_stats()
        return FeedbackStats(**stats)
    except Exception as e:
        logger.error(f"Error getting feedback stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
