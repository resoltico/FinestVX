"""Configuration models for APSW-backed FinestVX persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ftllexengine.runtime.cache_config import CacheConfig

__all__ = [
    "MANDATED_CACHE_CONFIG",
    "AuditContext",
    "DatabaseSnapshot",
    "PersistenceConfig",
]

MANDATED_CACHE_CONFIG = CacheConfig(
    write_once=True,
    integrity_strict=True,
    enable_audit=True,
    max_audit_entries=50000,
)
"""FinestVX-mandated FTLLexEngine cache policy for financial workloads."""


@dataclass(frozen=True, slots=True)
class AuditContext:
    """Structured write context captured by SQL audit triggers."""

    actor: str
    reason: str
    session_id: str | None = None

    def __post_init__(self) -> None:
        """Validate that actor and reason are non-empty."""
        if not self.actor.strip():
            msg = "actor must not be empty"
            raise ValueError(msg)
        if not self.reason.strip():
            msg = "reason must not be empty"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class PersistenceConfig:
    """Configuration for the SQLite persistence boundary."""

    database_path: Path | str
    busy_timeout_ms: int = 5000
    transaction_mode: str = "IMMEDIATE"
    wal_auto_checkpoint: int = 1000
    cache_config: CacheConfig = field(default=MANDATED_CACHE_CONFIG)

    def __post_init__(self) -> None:
        """Normalize filesystem paths and validate configuration."""
        database_path = Path(self.database_path)
        object.__setattr__(self, "database_path", database_path)
        if self.busy_timeout_ms <= 0:
            msg = "busy_timeout_ms must be positive"
            raise ValueError(msg)
        if self.wal_auto_checkpoint <= 0:
            msg = "wal_auto_checkpoint must be positive"
            raise ValueError(msg)
        allowed_modes = {"DEFERRED", "IMMEDIATE", "EXCLUSIVE"}
        if self.transaction_mode not in allowed_modes:
            msg = (
                "transaction_mode must be one of "
                f"{sorted(allowed_modes)}, got {self.transaction_mode}"
            )
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class DatabaseSnapshot:
    """Metadata for a generated on-disk database snapshot."""

    output_path: Path
    compressed: bool
    wal_frames: int
    checkpointed_frames: int
    bytes_written: int
