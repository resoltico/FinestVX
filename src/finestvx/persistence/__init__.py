"""Persistence exports for FinestVX."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from .config import (
    MANDATED_CACHE_CONFIG,
    AuditContext,
    DatabaseSnapshot,
    PersistenceConfig,
    ReadReplicaConfig,
)

if TYPE_CHECKING:
    from .backup import create_snapshot
    from .replica import ReadReplica
    from .store import (
        AsyncLedgerReader,
        AuditLogRecord,
        SqliteLedgerStore,
        StoreConnectionDebugSnapshot,
        StoreDebugSnapshot,
        StoreProfileEvent,
        StoreStatementCacheStats,
        StoreStatusCounter,
        StoreTraceEvent,
        StoreWalCommit,
        StoreWriteReceipt,
    )

__all__ = [
    "MANDATED_CACHE_CONFIG",
    "AsyncLedgerReader",
    "AuditContext",
    "AuditLogRecord",
    "DatabaseSnapshot",
    "PersistenceConfig",
    "ReadReplica",
    "ReadReplicaConfig",
    "SqliteLedgerStore",
    "StoreConnectionDebugSnapshot",
    "StoreDebugSnapshot",
    "StoreProfileEvent",
    "StoreStatementCacheStats",
    "StoreStatusCounter",
    "StoreTraceEvent",
    "StoreWalCommit",
    "StoreWriteReceipt",
    "create_snapshot",
]


def __getattr__(name: str) -> object:
    """Lazy-load APSW-backed components to keep package import lightweight."""
    if name in {
        "AsyncLedgerReader",
        "AuditLogRecord",
        "SqliteLedgerStore",
        "StoreConnectionDebugSnapshot",
        "StoreDebugSnapshot",
        "StoreProfileEvent",
        "StoreStatementCacheStats",
        "StoreStatusCounter",
        "StoreTraceEvent",
        "StoreWalCommit",
        "StoreWriteReceipt",
    }:
        return getattr(import_module(".store", __name__), name)
    if name == "create_snapshot":
        return getattr(import_module(".backup", __name__), name)
    if name == "ReadReplica":
        return getattr(import_module(".replica", __name__), name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
