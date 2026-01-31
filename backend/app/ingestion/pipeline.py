"""
Wine data ingestion pipeline.

Orchestrates the flow: adapter → normalizer → resolver → repository
"""

import hashlib
from datetime import datetime
from typing import Optional, Iterator

from .protocols import DataSourceAdapter, RawWineRecord, IngestionStats
from .normalizers import RatingNormalizer
from .entities import WineEntityResolver, CanonicalWine
from ..services.wine_repository import WineRepository


class IngestionPipeline:
    """
    Main ingestion pipeline for wine data.

    Coordinates:
    1. Reading from data source adapters
    2. Normalizing ratings
    3. Resolving entities (deduplication)
    4. Writing to database
    """

    def __init__(
        self,
        repository: Optional[WineRepository] = None,
        normalizer: Optional[RatingNormalizer] = None,
        resolver: Optional[WineEntityResolver] = None,
        batch_size: int = 1000,
    ):
        """
        Initialize pipeline.

        Args:
            repository: Wine repository (creates default if None)
            normalizer: Rating normalizer (creates default if None)
            resolver: Entity resolver (creates default if None)
            batch_size: Records per batch commit
        """
        self.repository = repository or WineRepository()
        self.normalizer = normalizer or RatingNormalizer()
        self.resolver = resolver or WineEntityResolver()
        self.batch_size = batch_size

    def ingest(
        self,
        adapter: DataSourceAdapter,
        skip_existing: bool = True,
        dry_run: bool = False,
    ) -> IngestionStats:
        """
        Ingest data from an adapter.

        Args:
            adapter: Data source adapter
            skip_existing: If True, skip if already ingested (by file hash)
            dry_run: If True, don't write to database

        Returns:
            IngestionStats with results
        """
        source_name = adapter.get_source_name()
        file_hash = adapter.get_file_hash()

        stats = IngestionStats(source_name=source_name)

        # Check if already ingested
        if skip_existing and file_hash and self._already_ingested(source_name, file_hash):
            stats.records_skipped = -1  # Signal skipped entire file
            return stats

        # Clear resolver for fresh run
        self.resolver.clear()

        # Process records
        for record in adapter.iter_records():
            stats.records_read += 1
            try:
                self._process_record(record, stats)
            except Exception as e:
                stats.errors.append(f"Row {record.row_number}: {str(e)}")
                stats.records_skipped += 1

            # Progress logging
            if stats.records_read % 10000 == 0:
                print(f"  Processed {stats.records_read} records...")

        # Write to database
        if not dry_run:
            self._write_to_database(stats)
            self._log_ingestion(source_name, file_hash, stats)

        return stats

    def _process_record(self, record: RawWineRecord, stats: IngestionStats):
        """Process a single record through normalizer and resolver."""
        # Normalize rating
        normalized_rating = self.normalizer.normalize(
            record.rating,
            record.rating_scale
        )

        # Resolve to canonical entity
        entity, is_new = self.resolver.resolve(
            wine_name=record.wine_name,
            normalized_rating=normalized_rating,
            original_rating=record.rating,
            original_scale=record.rating_scale,
            source_name=record.source_name,
            winery=record.winery,
            region=record.region,
            country=record.country,
            varietal=record.varietal,
            wine_type=record.wine_type,
        )

        stats.records_processed += 1
        if is_new:
            stats.records_added += 1
        else:
            stats.records_merged += 1

    def _write_to_database(self, stats: IngestionStats):
        """Write resolved entities to database."""
        entities = self.resolver.get_all_entities()
        wines = []

        for entity in entities:
            wines.append({
                "canonical_name": entity.canonical_name,
                "rating": entity.normalized_rating,
                "wine_type": entity.wine_type,
                "region": entity.region,
                "winery": entity.winery,
                "country": entity.country,
                "varietal": entity.varietal,
                "aliases": list(entity.aliases),
            })

        inserted, skipped = self.repository.bulk_insert(wines, self.batch_size)

        # Update stats
        stats.records_added = inserted
        stats.records_skipped += skipped

    def _already_ingested(self, source_name: str, file_hash: str) -> bool:
        """Check if this source/hash was already ingested."""
        conn = self.repository._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM ingestion_log
            WHERE source_name = ? AND file_hash = ?
            LIMIT 1
        """, (source_name, file_hash))
        return cursor.fetchone() is not None

    def _log_ingestion(self, source_name: str, file_hash: Optional[str], stats: IngestionStats):
        """Log ingestion to database."""
        conn = self.repository._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ingestion_log
            (source_name, file_hash, records_processed, records_added, records_updated, records_skipped)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            source_name,
            file_hash or "",
            stats.records_processed,
            stats.records_added,
            stats.records_updated,
            stats.records_skipped,
        ))
        conn.commit()

    def preview(
        self,
        adapter: DataSourceAdapter,
        limit: int = 10
    ) -> list[dict]:
        """
        Preview normalized records without writing.

        Args:
            adapter: Data source adapter
            limit: Max records to return

        Returns:
            List of normalized record dicts
        """
        results = []
        for i, record in enumerate(adapter.iter_records()):
            if i >= limit:
                break

            normalized_rating = self.normalizer.normalize(
                record.rating,
                record.rating_scale
            )

            results.append({
                "wine_name": record.wine_name,
                "original_rating": record.rating,
                "rating_scale": record.rating_scale,
                "normalized_rating": round(normalized_rating, 2),
                "winery": record.winery,
                "region": record.region,
                "country": record.country,
                "varietal": record.varietal,
            })

        return results
