-- Wine Shelf Scanner Database Schema
-- SQLite with FTS5 for fast text search

-- Core wines table
CREATE TABLE IF NOT EXISTS wines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE,
    rating REAL NOT NULL,
    wine_type TEXT,           -- red, white, rose, sparkling, etc.
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
    source_name TEXT NOT NULL,          -- 'kaggle_wine_reviews', 'vivino', etc.
    original_rating REAL NOT NULL,
    original_scale_min REAL NOT NULL,   -- e.g., 80 for Wine Enthusiast
    original_scale_max REAL NOT NULL,   -- e.g., 100 for Wine Enthusiast
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (wine_id) REFERENCES wines(id) ON DELETE CASCADE,
    UNIQUE(wine_id, source_name)
);

-- Ingestion log for idempotent re-runs
CREATE TABLE IF NOT EXISTS ingestion_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,            -- SHA256 of source file
    records_processed INTEGER NOT NULL,
    records_added INTEGER NOT NULL,
    records_updated INTEGER NOT NULL,
    records_skipped INTEGER NOT NULL,
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

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_wines_canonical_lower ON wines(LOWER(canonical_name));
CREATE INDEX IF NOT EXISTS idx_wines_winery ON wines(winery);
CREATE INDEX IF NOT EXISTS idx_wines_region ON wines(region);
CREATE INDEX IF NOT EXISTS idx_wines_country ON wines(country);
CREATE INDEX IF NOT EXISTS idx_wines_varietal ON wines(varietal);
CREATE INDEX IF NOT EXISTS idx_wine_aliases_name_lower ON wine_aliases(LOWER(alias_name));
CREATE INDEX IF NOT EXISTS idx_wine_aliases_wine_id ON wine_aliases(wine_id);
CREATE INDEX IF NOT EXISTS idx_wine_sources_wine_id ON wine_sources(wine_id);
