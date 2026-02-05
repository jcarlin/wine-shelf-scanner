"""
Alembic migration environment for SQLite.

Database path is resolved from DATABASE_PATH env var,
falling back to app/data/wines.db relative to backend/.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

# Add backend to Python path so app imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_database_url() -> str:
    """Get SQLite URL from environment or default."""
    db_path = os.getenv(
        "DATABASE_PATH",
        str(Path(__file__).parent.parent / "app" / "data" / "wines.db"),
    )
    return f"sqlite:///{db_path}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    from sqlalchemy import create_engine

    url = get_database_url()
    connectable = create_engine(url)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
