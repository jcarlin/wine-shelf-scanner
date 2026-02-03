# Wine Data Ingestion Guide

This document explains how to set up and run the wine data ingestion pipeline.

## Prerequisites

1. **Python 3.9+** with virtual environment
2. **Raw data files** - See `raw-data/README.md` for download instructions
3. **Backend dependencies installed**

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Quick Start

```bash
# Activate virtual environment
cd backend
source venv/bin/activate

# Ingest the smallest dataset first (for testing)
python scripts/ingest.py --source xwines

# Check database statistics
python scripts/ingest.py --stats
```

## Available Data Sources

| Source | Records | Description |
|--------|---------|-------------|
| `xwines` | ~1K wines | XWines Slim - quick testing |
| `xwines_full` | ~100K wines | XWines Full - **recommended for production** |
| `kaggle` | ~130K wines | Wine Enthusiast reviews |
| `kaggle130k` | ~130K wines | Kaggle 130K dataset |
| `vivino_brazil` | ~50K wines | Vivino Brazil data |
| `vivino_global` | Varies | Scraped Vivino data |

## CLI Commands

### Ingest a Single Source

```bash
python scripts/ingest.py --source xwines_full
```

### Ingest All Sources

```bash
python scripts/ingest.py --all
```

### Force Re-ingestion

By default, the pipeline skips sources that have already been ingested (based on file hash). Use `--force` to re-ingest:

```bash
python scripts/ingest.py --source kaggle --force
```

### Preview Data (Dry Run)

Preview the first 10 records without writing to database:

```bash
python scripts/ingest.py --preview xwines
```

### View Database Statistics

```bash
python scripts/ingest.py --stats
```

### Clear Database

```bash
python scripts/ingest.py --clear
```

### Benchmark Performance

```bash
python scripts/ingest.py --benchmark
```

## Pipeline Architecture

```
Raw Data Files
     ↓
[Adapter] → Reads CSV/JSON, yields RawWineRecord
     ↓
[Normalizer] → Converts ratings to 1-5 scale
     ↓
[Entity Resolver] → Deduplicates, merges across sources
     ↓
[Repository] → Writes to SQLite with FTS5
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| Pipeline | `app/ingestion/pipeline.py` | Orchestrates the flow |
| Adapters | `app/ingestion/adapters/` | Data source readers |
| Normalizer | `app/ingestion/normalizers.py` | Rating scale conversion |
| Resolver | `app/ingestion/entities.py` | Entity deduplication |
| Repository | `app/services/wine_repository.py` | Database access |

## Database Schema

The pipeline writes to SQLite with FTS5 full-text search:

- **wines** - Core wine records
- **wine_aliases** - Alternate names (kept in sync with FTS5)
- **wine_sources** - Original ratings from each source
- **ingestion_log** - Track what's been ingested

## Idempotency

The pipeline is idempotent - safe to run multiple times:

1. **File hash tracking** - Same file won't be re-processed
2. **UNIQUE constraints** - Duplicate wines are skipped
3. **Transaction safety** - Partial failures are tracked

## Troubleshooting

### "Required files not found"

```
Error: Required files not found for 'xwines_full':
  - /path/to/XWines_Full_100K_wines.csv
```

**Solution**: Download the required data files. See `raw-data/README.md`.

### "Already ingested (same file hash)"

The file has already been processed. Use `--force` to re-ingest:

```bash
python scripts/ingest.py --source kaggle --force
```

### Slow ingestion

For large datasets (100K+ wines), ingestion may take several minutes. Progress is logged every 10,000 records.

### Database locked errors

If you see "database is locked", ensure no other process is using `wines.db`. The pipeline uses WAL mode for better concurrency.

### FTS search not finding aliases

After ingestion, aliases are automatically indexed in FTS5. If search isn't working:

```bash
# Clear and re-ingest
python scripts/ingest.py --clear
python scripts/ingest.py --source xwines_full
```

## Adding New Data Sources

1. Create an adapter in `app/ingestion/adapters/`
2. Implement the `DataSourceAdapter` protocol
3. Register in `scripts/ingest.py` SOURCES dict
4. Add file validation in `validate_source_files()`

See existing adapters for examples:
- `config_adapter.py` - YAML-configured CSV adapter
- `xwines_adapter.py` - Custom adapter for XWines format
- `vivino_global_adapter.py` - Multi-file adapter

## Performance Targets

- **Full ingestion** (100K wines): < 5 minutes
- **Lookup performance**: < 50ms average
- **Database size**: ~50MB for 191K wines
