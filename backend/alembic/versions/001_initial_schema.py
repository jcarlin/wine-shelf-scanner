"""Initial schema - SQLite database with FTS5.

Revision ID: 001
Revises: None
Create Date: 2026-02-04

Creates core tables: wines, wine_aliases, wine_sources, ingestion_log,
wine_fts (FTS5), llm_ratings_cache, corrections, wine_reviews.

Note: bug_reports is created in migration 002.
Note: vision_cache is created in migration 003.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Complete schema SQL inlined for immutability.
# This ensures migration 001 always creates the same schema regardless
# of any future changes to external files.
SCHEMA_SQL = """
-- Core wines table
CREATE TABLE IF NOT EXISTS wines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE,
    rating REAL NOT NULL,
    wine_type TEXT,
    region TEXT,
    winery TEXT,
    country TEXT,
    varietal TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Wine aliases for alternate names
CREATE TABLE IF NOT EXISTS wine_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wine_id INTEGER NOT NULL,
    alias_name TEXT NOT NULL,
    FOREIGN KEY (wine_id) REFERENCES wines(id) ON DELETE CASCADE,
    UNIQUE(wine_id, alias_name)
);

-- Track original ratings from different sources
CREATE TABLE IF NOT EXISTS wine_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wine_id INTEGER NOT NULL,
    source_name TEXT NOT NULL,
    original_rating REAL NOT NULL,
    original_scale_min REAL NOT NULL,
    original_scale_max REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (wine_id) REFERENCES wines(id) ON DELETE CASCADE,
    UNIQUE(wine_id, source_name)
);

-- Ingestion log for idempotent re-runs
CREATE TABLE IF NOT EXISTS ingestion_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    records_processed INTEGER NOT NULL,
    records_added INTEGER NOT NULL,
    records_updated INTEGER NOT NULL,
    records_skipped INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'complete',
    run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_name, file_hash)
);

-- FTS5 virtual table for fast text search
CREATE VIRTUAL TABLE IF NOT EXISTS wine_fts USING fts5(
    canonical_name,
    aliases,
    region,
    winery,
    varietal,
    content='wines',
    content_rowid='id'
);

-- Triggers to keep FTS index in sync
CREATE TRIGGER IF NOT EXISTS wines_ai AFTER INSERT ON wines BEGIN
    INSERT INTO wine_fts(rowid, canonical_name, aliases, region, winery, varietal)
    VALUES (new.id, new.canonical_name, '', new.region, new.winery, new.varietal);
END;

CREATE TRIGGER IF NOT EXISTS wines_ad AFTER DELETE ON wines BEGIN
    INSERT INTO wine_fts(wine_fts, rowid, canonical_name, aliases, region, winery, varietal)
    VALUES ('delete', old.id, old.canonical_name, '', old.region, old.winery, old.varietal);
END;

CREATE TRIGGER IF NOT EXISTS wines_au AFTER UPDATE ON wines BEGIN
    INSERT INTO wine_fts(wine_fts, rowid, canonical_name, aliases, region, winery, varietal)
    VALUES ('delete', old.id, old.canonical_name, '', old.region, old.winery, old.varietal);
    INSERT INTO wine_fts(rowid, canonical_name, aliases, region, winery, varietal)
    VALUES (new.id, new.canonical_name, '', new.region, new.winery, new.varietal);
END;

-- Triggers to sync wine_aliases with FTS5 index
CREATE TRIGGER IF NOT EXISTS wine_aliases_ai AFTER INSERT ON wine_aliases BEGIN
    INSERT INTO wine_fts(wine_fts, rowid, canonical_name, aliases, region, winery, varietal)
    SELECT 'delete', w.id, w.canonical_name,
           COALESCE((SELECT GROUP_CONCAT(alias_name, ' ') FROM wine_aliases WHERE wine_id = w.id AND id != new.id), ''),
           w.region, w.winery, w.varietal
    FROM wines w WHERE w.id = new.wine_id;
    INSERT INTO wine_fts(rowid, canonical_name, aliases, region, winery, varietal)
    SELECT w.id, w.canonical_name,
           COALESCE((SELECT GROUP_CONCAT(alias_name, ' ') FROM wine_aliases WHERE wine_id = w.id), ''),
           w.region, w.winery, w.varietal
    FROM wines w WHERE w.id = new.wine_id;
END;

CREATE TRIGGER IF NOT EXISTS wine_aliases_ad AFTER DELETE ON wine_aliases BEGIN
    INSERT INTO wine_fts(wine_fts, rowid, canonical_name, aliases, region, winery, varietal)
    SELECT 'delete', w.id, w.canonical_name,
           COALESCE((SELECT GROUP_CONCAT(alias_name, ' ') FROM wine_aliases WHERE wine_id = w.id), ''),
           w.region, w.winery, w.varietal
    FROM wines w WHERE w.id = old.wine_id;
    INSERT INTO wine_fts(rowid, canonical_name, aliases, region, winery, varietal)
    SELECT w.id, w.canonical_name,
           COALESCE((SELECT GROUP_CONCAT(alias_name, ' ') FROM wine_aliases WHERE wine_id = w.id), ''),
           w.region, w.winery, w.varietal
    FROM wines w WHERE w.id = old.wine_id;
END;

-- LLM-estimated ratings cache for wines not in database
-- Includes extended metadata columns (wine_type, region, varietal, brand)
CREATE TABLE IF NOT EXISTS llm_ratings_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wine_name TEXT NOT NULL UNIQUE,
    estimated_rating REAL NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.7,
    llm_provider TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    wine_type TEXT,
    region TEXT,
    varietal TEXT,
    brand TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_wines_canonical_lower ON wines(LOWER(canonical_name));
CREATE INDEX IF NOT EXISTS idx_wines_winery ON wines(winery);
CREATE INDEX IF NOT EXISTS idx_wines_region ON wines(region);
CREATE INDEX IF NOT EXISTS idx_wines_country ON wines(country);
CREATE INDEX IF NOT EXISTS idx_wines_varietal ON wines(varietal);
CREATE INDEX IF NOT EXISTS idx_wine_aliases_name_lower ON wine_aliases(LOWER(alias_name));
CREATE INDEX IF NOT EXISTS idx_wine_aliases_wine_id ON wine_aliases(wine_id);
CREATE INDEX IF NOT EXISTS idx_wine_sources_wine_id ON wine_sources(wine_id);
CREATE INDEX IF NOT EXISTS idx_llm_ratings_cache_wine_name ON llm_ratings_cache(LOWER(wine_name));
CREATE INDEX IF NOT EXISTS idx_llm_ratings_cache_hit_count ON llm_ratings_cache(hit_count DESC);

-- User feedback/corrections for self-improving accuracy
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id TEXT NOT NULL,
    wine_name TEXT NOT NULL,
    ocr_text TEXT,
    is_correct BOOLEAN NOT NULL,
    corrected_name TEXT,
    device_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Individual wine reviews from various sources
CREATE TABLE IF NOT EXISTS wine_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wine_id INTEGER,
    source_name TEXT NOT NULL,
    user_id TEXT,
    rating REAL NOT NULL,
    review_date TEXT,
    vintage TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (wine_id) REFERENCES wines(id) ON DELETE SET NULL
);

-- Indexes for wine_reviews
CREATE INDEX IF NOT EXISTS idx_wine_reviews_wine_id ON wine_reviews(wine_id);
CREATE INDEX IF NOT EXISTS idx_wine_reviews_source ON wine_reviews(source_name);
CREATE INDEX IF NOT EXISTS idx_wine_reviews_rating ON wine_reviews(rating);

-- Indexes for corrections analysis
CREATE INDEX IF NOT EXISTS idx_corrections_wine_name ON corrections(LOWER(wine_name));
CREATE INDEX IF NOT EXISTS idx_corrections_is_correct ON corrections(is_correct);
CREATE INDEX IF NOT EXISTS idx_corrections_created_at ON corrections(created_at);
"""


def upgrade() -> None:
    # Use raw DBAPI connection for multi-statement SQL with triggers
    conn = op.get_bind()
    raw_conn = conn.connection.dbapi_connection
    raw_conn.executescript(SCHEMA_SQL)


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
