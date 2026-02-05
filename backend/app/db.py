"""
Database initialization helper.

Provides programmatic Alembic migration runner for:
- WineRepository initialization
- Test fixtures
- Any code that needs a fully migrated database

This is the single entry point for schema initialization.
All table creation happens through Alembic migrations.

Also provides BaseRepository class for thread-safe SQLite access.
"""

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from alembic import command
from alembic.config import Config as AlembicConfig

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).parent.parent


def ensure_schema(db_path: str) -> None:
    """
    Run Alembic migrations to head for the given database.

    This ensures the database has all tables defined by migrations.
    Safe to call multiple times - Alembic tracks applied migrations.

    Args:
        db_path: Absolute path to the SQLite database file.
                 Parent directory must exist.
    """
    # Create parent directory if needed
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    # Configure Alembic programmatically
    alembic_cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    # Suppress Alembic's default logging to avoid noise in tests
    logging.getLogger("alembic").setLevel(logging.WARNING)

    try:
        command.upgrade(alembic_cfg, "head")
        logger.debug(f"Schema initialized for {db_path}")
    except Exception as e:
        logger.error(f"Migration failed for {db_path}: {e}")
        raise


class BaseRepository:
    """
    Base class for thread-safe SQLite repositories.

    Provides common functionality for:
    - Thread-local connection pooling
    - Transaction context management
    - WAL mode for concurrent access
    """

    def __init__(self, db_path: Optional[str] = None, use_wal: bool = False):
        """
        Initialize repository.

        Args:
            db_path: Path to SQLite database. Defaults to Config.database_path()
            use_wal: Enable WAL mode for better concurrent access
        """
        if db_path is None:
            from app.config import Config
            db_path = Config.database_path()

        self.db_path = str(db_path)
        self._local = threading.local()
        self._use_wal = use_wal

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            if self._use_wal:
                # Enable foreign keys
                conn.execute("PRAGMA foreign_keys = ON")
                # WAL mode for better concurrent access
                conn.execute("PRAGMA journal_mode = WAL")
            self._local.connection = conn
        return self._local.connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Cursor]:
        """Context manager for transactions with automatic commit/rollback."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
