"""Backup helpers for the FinestVX SQLite store."""

from __future__ import annotations

from pathlib import Path

from .config import DatabaseSnapshot
from .store import SqliteLedgerStore

__all__ = ["create_snapshot"]


def create_snapshot(
    store: SqliteLedgerStore,
    output_path: Path | str,
    *,
    compress: bool = True,
) -> DatabaseSnapshot:
    """Create a WAL-consistent snapshot from the supplied ledger store."""
    return store.create_snapshot(output_path, compress=compress)
