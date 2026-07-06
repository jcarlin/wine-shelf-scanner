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
# Programmatic callers (app.db.ensure_schema, invoked at request time in
# production) set configure_logger=False: fileConfig was resetting the root
# logger to WARN + alembic's handler and disabling existing app loggers, so
# scan logs and llm_usage cost records vanished after the first request.
# The alembic CLI still configures logging from alembic.ini as before.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def get_database_url() -> str:
    """Get SQLite URL from environment, config, or default.

    Resolution order:
    1. DATABASE_PATH env var (Cloud Run, CI)
    2. sqlalchemy.url config option (programmatic callers via ensure_schema)
    3. Default: app/data/wines.db
    """
    # Check environment first
    env_path = os.getenv("DATABASE_PATH")
    if env_path:
        return f"sqlite:///{env_path}"

    # Check if set programmatically via config
    config_url = config.get_main_option("sqlalchemy.url")
    if config_url:
        return config_url

    # Default path
    default_path = Path(__file__).parent.parent / "app" / "data" / "wines.db"
    return f"sqlite:///{default_path}"


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
