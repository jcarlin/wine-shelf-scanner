"""
Database initialization helper.

Provides programmatic Alembic migration runner for:
- WineRepository initialization
- Test fixtures
- Any code that needs a fully migrated database

This is the single entry point for schema initialization.
All table creation happens through Alembic migrations.
"""

import logging
import os
from pathlib import Path

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
