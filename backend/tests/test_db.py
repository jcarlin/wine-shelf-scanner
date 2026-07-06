"""
ensure_schema (programmatic Alembic) must not silence application loggers.

alembic/env.py calls logging.config.fileConfig, whose default
disable_existing_loggers=True switches off every already-created logger —
in production that killed all scan/cost observability (the llm_usage
records and pipeline logs vanished after the first request-time
ensure_schema call).
"""

import logging

from app.db import ensure_schema


def test_ensure_schema_keeps_existing_loggers_alive(tmp_path, caplog):
    logger = logging.getLogger("app.services.llm_usage")
    assert not logger.disabled

    ensure_schema(str(tmp_path / "test.db"))

    assert not logger.disabled, (
        "alembic fileConfig disabled existing loggers — "
        "pass disable_existing_loggers=False in alembic/env.py"
    )
    with caplog.at_level(logging.INFO, logger="app.services.llm_usage"):
        logger.info("still alive")
    assert "still alive" in caplog.text
