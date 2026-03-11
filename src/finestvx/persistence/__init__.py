"""Persistence exports for FinestVX."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from .config import MANDATED_CACHE_CONFIG, AuditContext, DatabaseSnapshot, PersistenceConfig

if TYPE_CHECKING:
    from .backup import create_snapshot
    from .store import AuditLogRecord, SqliteLedgerStore, StoreDebugSnapshot

__all__ = [
    "MANDATED_CACHE_CONFIG",
    "AuditContext",
    "AuditLogRecord",
    "DatabaseSnapshot",
    "PersistenceConfig",
    "SqliteLedgerStore",
    "StoreDebugSnapshot",
    "create_snapshot",
]


def __getattr__(name: str) -> object:
    """Lazy-load APSW-backed components to keep package import lightweight."""
    if name == "AuditLogRecord":
        return getattr(import_module(".store", __name__), name)
    if name == "SqliteLedgerStore":
        return getattr(import_module(".store", __name__), name)
    if name == "StoreDebugSnapshot":
        return getattr(import_module(".store", __name__), name)
    if name == "create_snapshot":
        return getattr(import_module(".backup", __name__), name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
