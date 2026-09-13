"""Adapters that turn what a retailer already has into what an agent can read."""

from bondlayer.adapters.catalog import (
    CatalogReport,
    CsvCatalogAdapter,
    Diagnostic,
    Severity,
)

__all__ = ["CatalogReport", "CsvCatalogAdapter", "Diagnostic", "Severity"]
