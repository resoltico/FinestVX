"""Configuration models for APSW-backed FinestVX persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ftllexengine import (
    CacheConfig,
    require_int_in_range,
    require_non_empty_str,
    require_non_negative_int,
    require_positive_int,
)

__all__ = [
    "MANDATED_CACHE_CONFIG",
    "AuditContext",
    "DatabaseSnapshot",
    "PersistenceConfig",
    "ReadReplicaConfig",
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
        """Normalize and validate actor and reason."""
        object.__setattr__(self, "actor", require_non_empty_str(self.actor, "actor"))
        object.__setattr__(self, "reason", require_non_empty_str(self.reason, "reason"))


@dataclass(frozen=True, slots=True)
class PersistenceConfig:
    """Configuration for the SQLite persistence boundary."""

    database_path: Path | str
    busy_timeout_ms: int = 5000
    transaction_mode: str = "IMMEDIATE"
    wal_auto_checkpoint: int = 1000
    reader_connection_count: int = 4
    reader_checkout_timeout: float = 5.0
    writer_statement_cache_size: int = 256
    reader_statement_cache_size: int = 128
    reserve_bytes: int = 0
    telemetry_buffer_size: int = 0
    vfs_name: str | None = None
    cache_config: CacheConfig = field(default=MANDATED_CACHE_CONFIG)

    def __post_init__(self) -> None:
        """Normalize filesystem paths and validate configuration."""
        self._normalize_paths()
        self._validate_numeric_fields()
        self._validate_transaction_mode()

    def _normalize_paths(self) -> None:
        """Normalize filesystem-bound configuration fields."""
        object.__setattr__(self, "database_path", Path(self.database_path))
        if self.vfs_name is not None:
            object.__setattr__(
                self,
                "vfs_name",
                require_non_empty_str(self.vfs_name, "vfs_name"),
            )

    def _validate_numeric_fields(self) -> None:
        """Validate numeric persistence settings."""
        require_positive_int(self.busy_timeout_ms, "busy_timeout_ms")
        require_positive_int(self.wal_auto_checkpoint, "wal_auto_checkpoint")
        require_positive_int(self.reader_connection_count, "reader_connection_count")
        if self.reader_checkout_timeout <= 0:
            msg = "reader_checkout_timeout must be positive"
            raise ValueError(msg)
        require_non_negative_int(self.writer_statement_cache_size, "writer_statement_cache_size")
        require_non_negative_int(self.reader_statement_cache_size, "reader_statement_cache_size")
        require_int_in_range(self.reserve_bytes, 0, 255, "reserve_bytes")
        require_non_negative_int(self.telemetry_buffer_size, "telemetry_buffer_size")

    def _validate_transaction_mode(self) -> None:
        """Validate the SQLite transaction mode."""
        allowed_modes = {"DEFERRED", "IMMEDIATE", "EXCLUSIVE"}
        if self.transaction_mode not in allowed_modes:
            msg = (
                "transaction_mode must be one of "
                f"{sorted(allowed_modes)}, got {self.transaction_mode}"
            )
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ReadReplicaConfig:
    """Configuration for a periodically refreshed read-only WAL connection."""

    database_path: Path | str
    checkpoint_interval: float = 1.0
    reader_statement_cache_size: int = 128
    reserve_bytes: int = 0

    def __post_init__(self) -> None:
        """Normalize the path and validate connection settings."""
        object.__setattr__(self, "database_path", Path(self.database_path))
        if self.checkpoint_interval <= 0:
            msg = "checkpoint_interval must be positive"
            raise ValueError(msg)
        require_non_negative_int(self.reader_statement_cache_size, "reader_statement_cache_size")
        require_int_in_range(self.reserve_bytes, 0, 255, "reserve_bytes")


@dataclass(frozen=True, slots=True)
class DatabaseSnapshot:
    """Metadata for a generated on-disk database snapshot."""

    output_path: Path
    compressed: bool
    wal_frames: int
    checkpointed_frames: int
    bytes_written: int
