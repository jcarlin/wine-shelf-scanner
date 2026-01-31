"""
Data source adapters for wine ingestion.

Each adapter reads from a specific format and yields RawWineRecord objects.
"""

from .config_adapter import ConfigDrivenCSVAdapter

__all__ = ["ConfigDrivenCSVAdapter"]
