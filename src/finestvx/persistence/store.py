"""APSW-backed append-only ledger store for FinestVX."""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Buffer
from compression import zstd
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import blake2b
from pathlib import Path
from queue import Empty, Queue
from threading import Lock
from typing import TYPE_CHECKING, Any, cast

import apsw
import apsw.bestpractice as apsw_bestpractice
from ftllexengine.integrity import IntegrityContext, LedgerInvariantError, PersistenceIntegrityError

from finestvx.core.enums import TransactionState
from finestvx.core.serialization import book_from_mapping, book_to_mapping
from finestvx.core.validation import validate_chart_of_accounts, validate_transaction_balance
from finestvx.persistence.config import DatabaseSnapshot
from finestvx.persistence.schema import apply_sqlite_pragmas, install_schema

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from typing import Self

    from finestvx.core.models import Book, JournalTransaction
    from finestvx.legislation.protocols import LegislativeValidationResult
    from finestvx.persistence.config import AuditContext, PersistenceConfig

__all__ = [
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
]

type SQLiteBinding = int | float | Buffer | str | None
type SQLiteRow = tuple[SQLiteBinding, ...]
type AuditLogRow = tuple[
    int,
    str,
    str,
    str,
    str,
    str,
    str | None,
    int,
    str,
    str,
]

_STATUS_PARAMETERS: tuple[tuple[str, int], ...] = (
    ("cache_used", apsw.SQLITE_DBSTATUS_CACHE_USED),
    ("cache_hit", apsw.SQLITE_DBSTATUS_CACHE_HIT),
    ("cache_miss", apsw.SQLITE_DBSTATUS_CACHE_MISS),
    ("cache_spill", apsw.SQLITE_DBSTATUS_CACHE_SPILL),
    ("schema_used", apsw.SQLITE_DBSTATUS_SCHEMA_USED),
    ("stmt_used", apsw.SQLITE_DBSTATUS_STMT_USED),
)

_TRACE_CODE_NAMES = {
    apsw.SQLITE_TRACE_CLOSE: "SQLITE_TRACE_CLOSE",
    apsw.SQLITE_TRACE_PROFILE: "SQLITE_TRACE_PROFILE",
    apsw.SQLITE_TRACE_ROW: "SQLITE_TRACE_ROW",
    apsw.SQLITE_TRACE_STMT: "SQLITE_TRACE_STMT",
}


@dataclass(frozen=True, slots=True)
class AuditLogRecord:
    """Single audit row emitted by SQLite triggers."""

    seq: int
    table_name: str
    operation: str
    row_pk: str
    actor: str
    reason: str
    session_id: str | None
    monotonic_ms: int
    row_signature: str
    row_payload: str


@dataclass(frozen=True, slots=True)
class StoreStatementCacheStats:
    """Statement-cache counters reported by APSW."""

    size: int
    evictions: int
    no_cache: int
    hits: int
    misses: int
    no_vdbe: int
    too_big: int
    max_cacheable_bytes: int


@dataclass(frozen=True, slots=True)
class StoreStatusCounter:
    """One APSW status counter measurement."""

    name: str
    current: int
    highwater: int


@dataclass(frozen=True, slots=True)
class StoreConnectionDebugSnapshot:
    """Observability snapshot for one APSW connection."""

    label: str
    readonly: bool
    data_version: int
    statement_cache: StoreStatementCacheStats
    status_counters: tuple[StoreStatusCounter, ...]


@dataclass(frozen=True, slots=True)
class StoreWalCommit:
    """Last observed WAL commit event from the writer connection."""

    database_name: str
    pages_in_wal: int


@dataclass(frozen=True, slots=True)
class StoreTraceEvent:
    """Bounded SQL trace event captured from APSW."""

    connection_label: str
    code: str
    statement_id: int | None
    sql: str | None
    trigger: bool
    total_changes: int | None


@dataclass(frozen=True, slots=True)
class StoreProfileEvent:
    """Bounded SQL profile event captured from APSW."""

    connection_label: str
    sql: str
    nanoseconds: int


@dataclass(frozen=True, slots=True)
class StoreWriteReceipt:
    """Typed changeset metadata for one committed write operation."""

    data_version: int
    changed_tables: tuple[str, ...]
    change_count: int
    indirect_change_count: int
    changeset: bytes
    patchset: bytes
    changeset_size_bytes: int
    patchset_size_bytes: int
    memory_used_bytes: int
    last_wal_commit: StoreWalCommit | None


@dataclass(frozen=True, slots=True)
class StoreDebugSnapshot:
    """Non-invasive debug snapshot for the APSW-backed ledger store."""

    database_path: Path
    reserve_bytes: int
    book_count: int
    transaction_count: int
    entry_count: int
    audit_row_count: int
    writer: StoreConnectionDebugSnapshot
    readers: tuple[StoreConnectionDebugSnapshot, ...]
    last_wal_commit: StoreWalCommit | None
    recent_trace_events: tuple[StoreTraceEvent, ...]
    recent_profile_events: tuple[StoreProfileEvent, ...]


@dataclass(slots=True)
class _AuditState:
    """Mutable per-connection audit context exposed to SQLite scalar functions."""

    actor: str = "system"
    reason: str = "schema/bootstrap"
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class _ReaderHandle:
    """Named read-only APSW connection managed by the reader pool."""

    label: str
    connection: apsw.Connection


def _fetchall(
    connection: apsw.Connection,
    sql: str,
    bindings: tuple[SQLiteBinding, ...] = (),
) -> list[SQLiteRow]:
    """Execute a query and return all rows eagerly."""
    cursor = connection.cursor()
    cursor.execute(sql, bindings)
    return cursor.fetchall()


def _fetch_scalar_int(
    connection: apsw.Connection,
    sql: str,
    bindings: tuple[SQLiteBinding, ...] = (),
) -> int:
    """Execute a scalar query and normalize the integer result."""
    row = connection.execute(sql, bindings).fetchone()
    if row is None or isinstance(row[0], bool) or not isinstance(row[0], int):
        msg = f"Expected scalar integer result for SQL query: {sql}"
        raise TypeError(msg)
    return cast("int", row[0])


async def _fetchall_async(
    connection: apsw.Connection,
    sql: str,
    bindings: tuple[SQLiteBinding, ...] = (),
) -> list[SQLiteRow]:
    """Execute an async query and return all rows eagerly."""
    async_connection = cast("Any", connection)
    cursor = await async_connection.execute(sql, bindings)
    return cast("list[SQLiteRow]", await cursor.fetchall())


async def _fetchone_async(
    connection: apsw.Connection,
    sql: str,
    bindings: tuple[SQLiteBinding, ...] = (),
) -> SQLiteRow | None:
    """Execute an async query and return one row."""
    async_connection = cast("Any", connection)
    cursor = await async_connection.execute(sql, bindings)
    return cast("SQLiteRow | None", await cursor.fetchone())


async def _build_async_status_counters(
    connection: apsw.Connection,
) -> tuple[StoreStatusCounter, ...]:
    """Collect a deterministic subset of APSW status counters from an async connection."""
    async_connection = cast("Any", connection)
    counters: list[StoreStatusCounter] = []
    for name, op in _STATUS_PARAMETERS:
        current, highwater = await async_connection.status(op)
        counters.append(
            StoreStatusCounter(
                name=name,
                current=current,
                highwater=highwater,
            )
        )
    return tuple(counters)


def _build_statement_cache_stats(connection: apsw.Connection) -> StoreStatementCacheStats:
    """Normalize APSW cache-stats dicts into a typed snapshot."""
    stats = connection.cache_stats()
    return StoreStatementCacheStats(
        size=int(stats["size"]),
        evictions=int(stats["evictions"]),
        no_cache=int(stats["no_cache"]),
        hits=int(stats["hits"]),
        misses=int(stats["misses"]),
        no_vdbe=int(stats["no_vdbe"]),
        too_big=int(stats["too_big"]),
        max_cacheable_bytes=int(stats["max_cacheable_bytes"]),
    )


def _build_status_counters(connection: apsw.Connection) -> tuple[StoreStatusCounter, ...]:
    """Collect a deterministic subset of APSW connection status counters."""
    return tuple(
        StoreStatusCounter(
            name=name,
            current=current,
            highwater=highwater,
        )
        for name, op in _STATUS_PARAMETERS
        for current, highwater in (connection.status(op),)
    )


def _build_connection_debug_snapshot(
    label: str,
    connection: apsw.Connection,
) -> StoreConnectionDebugSnapshot:
    """Build a typed debug snapshot for one APSW connection."""
    return StoreConnectionDebugSnapshot(
        label=label,
        readonly=connection.readonly("main"),
        data_version=connection.data_version(),
        statement_cache=_build_statement_cache_stats(connection),
        status_counters=_build_status_counters(connection),
    )


def _build_audit_log_records(rows: Iterable[SQLiteRow]) -> tuple[AuditLogRecord, ...]:
    """Normalize raw rows into immutable audit log records."""
    return tuple(AuditLogRecord(*cast("AuditLogRow", row)) for row in rows)


def _build_book_payload(
    book_row: SQLiteRow,
    account_rows: Iterable[SQLiteRow],
    period_rows: Iterable[SQLiteRow],
    transaction_rows: Iterable[SQLiteRow],
    entry_rows_by_reference: dict[str, list[SQLiteRow]],
) -> dict[str, object]:
    """Construct the deterministic book payload consumed by core deserializers."""
    accounts = [
        {
            "code": row[0],
            "name": row[1],
            "normal_side": row[2],
            "currency": row[3],
            "parent_code": row[4],
            "allow_posting": bool(row[5]),
            "active": bool(row[6]),
        }
        for row in account_rows
    ]
    periods = [
        {
            "period": {
                "fiscal_year": row[0],
                "quarter": row[1],
                "month": row[2],
            },
            "start_date": row[3],
            "end_date": row[4],
            "state": row[5],
        }
        for row in period_rows
    ]
    transactions: list[dict[str, object]] = []
    for tx_row in transaction_rows:
        entries = [
            {
                "account_code": entry_row[0],
                "side": entry_row[1],
                "amount": entry_row[2],
                "currency": entry_row[3],
                "description": entry_row[4],
                "tax_rate": entry_row[5],
            }
            for entry_row in entry_rows_by_reference[cast("str", tx_row[0])]
        ]
        period_payload: dict[str, int] | None
        if tx_row[4] is None:
            period_payload = None
        else:
            period_payload = {
                "fiscal_year": cast("int", tx_row[4]),
                "quarter": cast("int", tx_row[5]),
                "month": cast("int", tx_row[6]),
            }
        transactions.append(
            {
                "reference": tx_row[0],
                "posted_at": tx_row[1],
                "description": tx_row[2],
                "state": tx_row[3],
                "period": period_payload,
                "reversal_of": tx_row[7],
                "entries": entries,
            }
        )
    return {
        "code": book_row[0],
        "name": book_row[1],
        "base_currency": book_row[2],
        "fiscal_calendar": {"start_month": book_row[3]},
        "legislative_pack": book_row[4],
        "accounts": accounts,
        "periods": periods,
        "transactions": transactions,
    }


def _load_book_from_connection(connection: apsw.Connection, book_code: str) -> Book:
    """Load a complete immutable book aggregate from one APSW connection."""
    book_row = connection.execute(
        """
        SELECT book_code, name, base_currency, fiscal_start_month, legislative_pack
        FROM books
        WHERE book_code = ?
        """,
        (book_code,),
    ).fetchone()
    if book_row is None:
        msg = f"Unknown book: {book_code}"
        raise KeyError(msg)

    account_rows = _fetchall(
        connection,
        """
        SELECT code, name, normal_side, currency, parent_code, allow_posting, active
        FROM accounts
        WHERE book_code = ?
        ORDER BY code
        """,
        (book_code,),
    )
    period_rows = _fetchall(
        connection,
        """
        SELECT fiscal_year, quarter, month, start_date, end_date, state
        FROM periods
        WHERE book_code = ?
        ORDER BY start_date, end_date, fiscal_year, quarter, month
        """,
        (book_code,),
    )
    transaction_rows = _fetchall(
        connection,
        """
        SELECT reference, posted_at, description, state, period_fiscal_year, period_quarter,
               period_month, reversal_of
        FROM transactions
        WHERE book_code = ?
        ORDER BY posted_at, reference
        """,
        (book_code,),
    )
    entry_rows_by_reference = {
        cast("str", tx_row[0]): _fetchall(
            connection,
            """
            SELECT account_code, side, amount, currency, description, tax_rate
            FROM entries
            WHERE book_code = ? AND transaction_reference = ?
            ORDER BY line_no
            """,
            (book_code, cast("str", tx_row[0])),
        )
        for tx_row in transaction_rows
    }
    integrity_context = IntegrityContext(
        component="persistence.store",
        operation="load_book",
        key=book_code,
        timestamp=time.monotonic(),
        wall_time_unix=time.time(),
    )
    try:
        book = book_from_mapping(
            _build_book_payload(
                book_row=cast("SQLiteRow", book_row),
                account_rows=account_rows,
                period_rows=period_rows,
                transaction_rows=transaction_rows,
                entry_rows_by_reference=entry_rows_by_reference,
            )
        )
    except (TypeError, ValueError) as exc:
        msg = f"Stored book {book_code!r} could not be deserialized: {exc}"
        raise PersistenceIntegrityError(msg, integrity_context) from exc
    try:
        validate_chart_of_accounts(book.accounts)
    except (TypeError, ValueError) as exc:
        msg = f"Stored book {book_code!r} failed chart-of-accounts invariant: {exc}"
        raise LedgerInvariantError(
            msg,
            integrity_context,
            invariant_code="COA_INVARIANT",
            entity_ref=book_code,
        ) from exc
    for tx in book.transactions:
        try:
            validate_transaction_balance(tx)
        except (TypeError, ValueError) as exc:
            msg = (
                f"Stored transaction {tx.reference!r} in book {book_code!r} "
                f"failed balance invariant: {exc}"
            )
            raise LedgerInvariantError(
                msg,
                integrity_context,
                invariant_code="TRANSACTION_BALANCE",
                entity_ref=tx.reference,
            ) from exc
    return book


async def _load_book_from_async_connection(connection: apsw.Connection, book_code: str) -> Book:
    """Load a complete immutable book aggregate from one async APSW connection."""
    book_row = await _fetchone_async(
        connection,
        """
        SELECT book_code, name, base_currency, fiscal_start_month, legislative_pack
        FROM books
        WHERE book_code = ?
        """,
        (book_code,),
    )
    if book_row is None:
        msg = f"Unknown book: {book_code}"
        raise KeyError(msg)
    account_rows = await _fetchall_async(
        connection,
        """
        SELECT code, name, normal_side, currency, parent_code, allow_posting, active
        FROM accounts
        WHERE book_code = ?
        ORDER BY code
        """,
        (book_code,),
    )
    period_rows = await _fetchall_async(
        connection,
        """
        SELECT fiscal_year, quarter, month, start_date, end_date, state
        FROM periods
        WHERE book_code = ?
        ORDER BY start_date, end_date, fiscal_year, quarter, month
        """,
        (book_code,),
    )
    transaction_rows = await _fetchall_async(
        connection,
        """
        SELECT reference, posted_at, description, state, period_fiscal_year, period_quarter,
               period_month, reversal_of
        FROM transactions
        WHERE book_code = ?
        ORDER BY posted_at, reference
        """,
        (book_code,),
    )
    entry_rows_by_reference: dict[str, list[SQLiteRow]] = {}
    for tx_row in transaction_rows:
        reference = cast("str", tx_row[0])
        entry_rows_by_reference[reference] = await _fetchall_async(
            connection,
            """
            SELECT account_code, side, amount, currency, description, tax_rate
            FROM entries
            WHERE book_code = ? AND transaction_reference = ?
            ORDER BY line_no
            """,
            (book_code, reference),
        )
    integrity_context = IntegrityContext(
        component="persistence.store",
        operation="load_book",
        key=book_code,
        timestamp=time.monotonic(),
        wall_time_unix=time.time(),
    )
    try:
        book = book_from_mapping(
            _build_book_payload(
                book_row=book_row,
                account_rows=account_rows,
                period_rows=period_rows,
                transaction_rows=transaction_rows,
                entry_rows_by_reference=entry_rows_by_reference,
            )
        )
    except (TypeError, ValueError) as exc:
        msg = f"Stored book {book_code!r} could not be deserialized: {exc}"
        raise PersistenceIntegrityError(msg, integrity_context) from exc
    try:
        validate_chart_of_accounts(book.accounts)
    except (TypeError, ValueError) as exc:
        msg = f"Stored book {book_code!r} failed chart-of-accounts invariant: {exc}"
        raise LedgerInvariantError(
            msg,
            integrity_context,
            invariant_code="COA_INVARIANT",
            entity_ref=book_code,
        ) from exc
    for tx in book.transactions:
        try:
            validate_transaction_balance(tx)
        except (TypeError, ValueError) as exc:
            msg = (
                f"Stored transaction {tx.reference!r} in book {book_code!r} "
                f"failed balance invariant: {exc}"
            )
            raise LedgerInvariantError(
                msg,
                integrity_context,
                invariant_code="TRANSACTION_BALANCE",
                entity_ref=tx.reference,
            ) from exc
    return book


def _build_write_receipt(
    session: apsw.Session,
    *,
    data_version: int,
    last_wal_commit: StoreWalCommit | None,
) -> StoreWriteReceipt:
    """Convert an APSW session into a typed write receipt."""
    changeset = session.changeset()
    patchset = session.patchset()
    changed_tables: list[str] = []
    seen_tables: set[str] = set()
    change_count = 0
    indirect_change_count = 0
    for change in apsw.Changeset.iter(changeset):
        change_count += 1
        if change.indirect:
            indirect_change_count += 1
        if change.name not in seen_tables:
            seen_tables.add(change.name)
            changed_tables.append(change.name)
    return StoreWriteReceipt(
        data_version=data_version,
        changed_tables=tuple(changed_tables),
        change_count=change_count,
        indirect_change_count=indirect_change_count,
        changeset=changeset,
        patchset=patchset,
        changeset_size_bytes=len(changeset),
        patchset_size_bytes=len(patchset),
        memory_used_bytes=int(session.memory_used),
        last_wal_commit=last_wal_commit,
    )


class AsyncLedgerReader:
    """Async read-only APSW facade for FinestVX persistence snapshots."""

    __slots__ = ("_config", "_connection")

    def __init__(self, config: PersistenceConfig, connection: Any) -> None:
        """Store the async APSW connection and its configuration."""
        self._config = config
        self._connection = connection

    @classmethod
    async def open(cls, config: PersistenceConfig) -> Self:
        """Open an async read-only APSW connection for FinestVX reads."""
        apsw_bestpractice.library_logging()
        connection = await apsw.Connection.as_async(
            str(Path(config.database_path)),
            flags=apsw.SQLITE_OPEN_READONLY,
            vfs=config.vfs_name,
            statementcachesize=config.reader_statement_cache_size,
        )
        async_connection = cast("Any", connection)
        await async_connection.set_busy_timeout(config.busy_timeout_ms)
        await async_connection.config(apsw.SQLITE_DBCONFIG_DQS_DML, 0)
        await async_connection.config(apsw.SQLITE_DBCONFIG_DQS_DDL, 0)
        if not await async_connection.readonly("main"):
            connection.close()
            msg = "Async APSW reader connection must be opened read-only"
            raise RuntimeError(msg)
        reserve_bytes = await async_connection.reserve_bytes()
        if reserve_bytes != config.reserve_bytes:
            connection.close()
            msg = (
                "Async APSW reader reserve_bytes mismatch: "
                f"expected {config.reserve_bytes}, got {reserve_bytes}"
            )
            raise ValueError(msg)
        return cls(config, connection)

    async def list_book_codes(self) -> tuple[str, ...]:
        """Return all known book codes in deterministic order."""
        rows = await _fetchall_async(
            cast("Any", self._connection),
            "SELECT book_code FROM books ORDER BY book_code",
        )
        return tuple(cast("str", row[0]) for row in rows)

    async def load_book(self, book_code: str) -> Book:
        """Load a complete immutable book aggregate from the async reader."""
        return await _load_book_from_async_connection(cast("Any", self._connection), book_code)

    async def iter_audit_log(self, *, limit: int | None = None) -> tuple[AuditLogRecord, ...]:
        """Return audit log rows ordered by sequence number."""
        sql = (
            "SELECT seq, table_name, operation, row_pk, actor, reason, session_id, "
            "monotonic_ms, row_signature, row_payload "
            "FROM audit_log ORDER BY seq"
        )
        bindings: tuple[SQLiteBinding, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            bindings = (limit,)
        return _build_audit_log_records(
            await _fetchall_async(cast("Any", self._connection), sql, bindings)
        )

    async def debug_snapshot(self) -> StoreConnectionDebugSnapshot:
        """Return APSW telemetry for the async reader connection."""
        connection = cast("Any", self._connection)
        return StoreConnectionDebugSnapshot(
            label="async-reader",
            readonly=await connection.readonly("main"),
            data_version=await connection.data_version(),
            statement_cache=_build_statement_cache_stats(connection),
            status_counters=await _build_async_status_counters(connection),
        )

    def close(self) -> None:
        """Close the underlying APSW async connection."""
        self._connection.close()


class SqliteLedgerStore:
    """SQLite WAL store with append-only rules and typed APSW observability."""

    __slots__ = (
        "_audit_state",
        "_config",
        "_last_wal_commit",
        "_profile_events",
        "_reader_handles",
        "_reader_pool",
        "_telemetry_lock",
        "_trace_events",
        "_writer_connection",
        "_writer_lock",
    )

    def __init__(self, config: PersistenceConfig) -> None:
        """Open the SQLite database, register functions, install schema, and prepare readers."""
        self._config = config
        database_path = Path(self._config.database_path)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        database_existed = database_path.exists() and database_path.stat().st_size > 0

        apsw_bestpractice.library_logging()

        self._audit_state = _AuditState()
        self._writer_lock = Lock()
        self._telemetry_lock = Lock()
        self._last_wal_commit: StoreWalCommit | None = None
        self._trace_events: deque[StoreTraceEvent] = deque(
            maxlen=self._config.telemetry_buffer_size
        )
        self._profile_events: deque[StoreProfileEvent] = deque(
            maxlen=self._config.telemetry_buffer_size
        )

        self._writer_connection = apsw.Connection(
            str(database_path),
            statementcachesize=self._config.writer_statement_cache_size,
            vfs=self._config.vfs_name,
        )
        self._writer_connection.transaction_mode = self._config.transaction_mode
        self._writer_connection.set_busy_timeout(self._config.busy_timeout_ms)
        apsw_bestpractice.connection_dqs(self._writer_connection)
        apsw_bestpractice.connection_optimize(self._writer_connection)
        self._apply_reserve_bytes(database_existed=database_existed)
        self._register_sql_functions()
        apply_sqlite_pragmas(
            self._writer_connection,
            wal_auto_checkpoint=self._config.wal_auto_checkpoint,
        )
        self._attach_observers("writer", self._writer_connection)
        install_schema(self._writer_connection)

        self._reader_handles = tuple(
            self._open_reader_handle(index + 1)
            for index in range(self._config.reader_connection_count)
        )
        self._reader_pool: Queue[_ReaderHandle] = Queue(maxsize=len(self._reader_handles))
        for handle in self._reader_handles:
            self._reader_pool.put(handle)

    @property
    def database_path(self) -> Path:
        """Return the on-disk SQLite database path."""
        return cast("Path", self._config.database_path)

    def close(self) -> None:
        """Close all APSW connections held by the store."""
        with self._writer_lock:
            self._writer_connection.pragma("optimize")
            self._writer_connection.close()
        for handle in self._reader_handles:
            handle.connection.close()

    def _apply_reserve_bytes(self, *, database_existed: bool) -> None:
        """Enforce the configured reserve-bytes policy without migrations."""
        current_reserve = self._writer_connection.reserve_bytes()
        if database_existed:
            if current_reserve != self._config.reserve_bytes:
                msg = (
                    "Existing SQLite database reserve_bytes mismatch: "
                    f"expected {self._config.reserve_bytes}, got {current_reserve}"
                )
                raise ValueError(msg)
            return
        if current_reserve != self._config.reserve_bytes:
            self._writer_connection.reserve_bytes(reserve=self._config.reserve_bytes)
            self._writer_connection.execute("VACUUM")
        actual_reserve = self._writer_connection.reserve_bytes()
        if actual_reserve != self._config.reserve_bytes:
            msg = (
                "SQLite reserve_bytes configuration failed: "
                f"expected {self._config.reserve_bytes}, got {actual_reserve}"
            )
            raise ValueError(msg)

    def _open_reader_handle(self, index: int) -> _ReaderHandle:
        """Open one read-only APSW connection and validate its invariants."""
        connection = apsw.Connection(
            str(self.database_path),
            flags=apsw.SQLITE_OPEN_READONLY,
            statementcachesize=self._config.reader_statement_cache_size,
            vfs=self._config.vfs_name,
        )
        connection.set_busy_timeout(self._config.busy_timeout_ms)
        apsw_bestpractice.connection_dqs(connection)
        apsw_bestpractice.connection_optimize(connection)
        self._attach_observers(f"reader-{index}", connection)
        if not connection.readonly("main"):
            msg = f"Reader connection reader-{index} must be opened read-only"
            raise RuntimeError(msg)
        reserve_bytes = connection.reserve_bytes()
        if reserve_bytes != self._config.reserve_bytes:
            msg = (
                f"Reader connection reader-{index} reserve_bytes mismatch: "
                f"expected {self._config.reserve_bytes}, got {reserve_bytes}"
            )
            raise ValueError(msg)
        return _ReaderHandle(label=f"reader-{index}", connection=connection)

    def _attach_observers(self, label: str, connection: apsw.Connection) -> None:
        """Attach APSW observability hooks to one connection."""
        if label == "writer":
            connection.set_wal_hook(self._wal_hook)
        if self._config.telemetry_buffer_size == 0:
            return
        connection.trace_v2(
            apsw.SQLITE_TRACE_STMT,
            lambda event: self._record_trace_event(label, event),
            id=f"{label}-trace",
        )
        connection.set_profile(
            lambda sql, nanoseconds: self._record_profile_event(label, sql, nanoseconds)
        )

    def _record_trace_event(self, label: str, event: dict[str, object]) -> None:
        """Append one bounded trace event."""
        with self._telemetry_lock:
            self._trace_events.append(
                StoreTraceEvent(
                    connection_label=label,
                    code=_TRACE_CODE_NAMES.get(
                        cast("int", event["code"]),
                        f"UNKNOWN:{event['code']}",
                    ),
                    statement_id=cast("int | None", event.get("id")),
                    sql=cast("str | None", event.get("sql")),
                    trigger=bool(event.get("trigger", False)),
                    total_changes=cast("int | None", event.get("total_changes")),
                )
            )

    def _record_profile_event(self, label: str, sql: str, nanoseconds: int) -> None:
        """Append one bounded profile event."""
        with self._telemetry_lock:
            self._profile_events.append(
                StoreProfileEvent(
                    connection_label=label,
                    sql=sql,
                    nanoseconds=nanoseconds,
                )
            )

    def _wal_hook(self, connection: apsw.Connection, database_name: str, pages_in_wal: int) -> int:
        """Capture the latest WAL commit metadata."""
        del connection
        with self._telemetry_lock:
            self._last_wal_commit = StoreWalCommit(
                database_name=database_name,
                pages_in_wal=pages_in_wal,
            )
        return apsw.SQLITE_OK

    def _register_sql_functions(self) -> None:
        """Expose deterministic helper functions to SQLite triggers."""
        def blake2_hex(*args: SQLiteBinding) -> str:
            payload = args[0] if args else None
            return blake2b(str(payload).encode("utf-8"), digest_size=16).hexdigest()

        def audit_actor(*args: SQLiteBinding) -> str:
            del args
            return self._audit_state.actor

        def audit_reason(*args: SQLiteBinding) -> str:
            del args
            return self._audit_state.reason

        def audit_session_id(*args: SQLiteBinding) -> str | None:
            del args
            return self._audit_state.session_id

        def monotonic_ms(*args: SQLiteBinding) -> int:
            del args
            return time.monotonic_ns() // 1_000_000

        self._writer_connection.create_scalar_function(
            "blake2_hex",
            blake2_hex,
            1,
            deterministic=True,
        )
        self._writer_connection.create_scalar_function(
            "audit_actor",
            audit_actor,
            0,
        )
        self._writer_connection.create_scalar_function(
            "audit_reason",
            audit_reason,
            0,
        )
        self._writer_connection.create_scalar_function(
            "audit_session_id",
            audit_session_id,
            0,
        )
        self._writer_connection.create_scalar_function(
            "monotonic_ms",
            monotonic_ms,
            0,
        )

    @contextmanager
    def _audit_context(self, context: AuditContext) -> Iterator[None]:
        """Temporarily expose the write audit context to SQLite triggers."""
        previous = _AuditState(
            actor=self._audit_state.actor,
            reason=self._audit_state.reason,
            session_id=self._audit_state.session_id,
        )
        self._audit_state.actor = context.actor
        self._audit_state.reason = context.reason
        self._audit_state.session_id = context.session_id
        try:
            yield
        finally:
            self._audit_state.actor = previous.actor
            self._audit_state.reason = previous.reason
            self._audit_state.session_id = previous.session_id

    @contextmanager
    def _borrow_reader(self) -> Iterator[_ReaderHandle]:
        """Borrow one reader connection from the bounded pool."""
        try:
            handle = self._reader_pool.get(timeout=self._config.reader_checkout_timeout)
        except Empty as error:
            msg = "Timed out waiting for a SQLite reader connection"
            raise TimeoutError(msg) from error
        try:
            yield handle
        finally:
            self._reader_pool.put(handle)

    @contextmanager
    def _borrow_all_readers(self) -> Iterator[tuple[_ReaderHandle, ...]]:
        """Borrow every reader connection for a consistent debug snapshot."""
        borrowed: list[_ReaderHandle] = []
        try:
            for _ in self._reader_handles:
                try:
                    borrowed.append(
                        self._reader_pool.get(timeout=self._config.reader_checkout_timeout)
                    )
                except Empty as error:
                    msg = "Timed out waiting for SQLite reader telemetry access"
                    raise TimeoutError(msg) from error
            yield tuple(borrowed)
        finally:
            for handle in reversed(borrowed):
                self._reader_pool.put(handle)

    @contextmanager
    def _capture_write_session(self) -> Iterator[apsw.Session]:
        """Capture one APSW session for a single committed write operation."""
        session = apsw.Session(self._writer_connection, "main")
        session.attach()
        try:
            yield session
        finally:
            session.close()

    def _last_wal_commit_snapshot(self) -> StoreWalCommit | None:
        """Return a stable copy of the last observed WAL commit."""
        with self._telemetry_lock:
            return self._last_wal_commit

    def _execute_write(
        self,
        operation: Callable[[], None],
        *,
        audit_context: AuditContext,
    ) -> StoreWriteReceipt:
        """Run one writer operation and return its typed APSW changeset receipt."""
        with self._writer_lock, self._capture_write_session() as session, self._audit_context(
            audit_context
        ):
            with self._writer_connection:
                operation()
            return _build_write_receipt(
                session,
                data_version=self._writer_connection.data_version(),
                last_wal_commit=self._last_wal_commit_snapshot(),
            )

    def create_book(self, book: Book, *, audit_context: AuditContext) -> StoreWriteReceipt:
        """Persist a new book and its immutable bootstrap data."""
        validate_chart_of_accounts(book.accounts)

        def operation() -> None:
            self._writer_connection.execute(
                """
                INSERT INTO books(
                    book_code,
                    name,
                    base_currency,
                    fiscal_start_month,
                    legislative_pack
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    book.code,
                    book.name,
                    book.base_currency,
                    book.fiscal_calendar.start_month,
                    book.legislative_pack,
                ),
            )
            for account in book.accounts:
                self._writer_connection.execute(
                    """
                    INSERT INTO accounts(
                        book_code,
                        code,
                        name,
                        normal_side,
                        currency,
                        parent_code,
                        allow_posting,
                        active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        book.code,
                        account.code,
                        account.name,
                        account.normal_side.value,
                        account.currency,
                        account.parent_code,
                        int(account.allow_posting),
                        int(account.active),
                    ),
                )
            for period in book.periods:
                self._writer_connection.execute(
                    """
                    INSERT INTO periods(
                        book_code,
                        fiscal_year,
                        quarter,
                        month,
                        start_date,
                        end_date,
                        state
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        book.code,
                        period.period.fiscal_year,
                        period.period.quarter,
                        period.period.month,
                        period.start_date.isoformat(),
                        period.end_date.isoformat(),
                        period.state.value,
                    ),
                )
            for transaction in book.transactions:
                self._insert_transaction_rows(book.code, transaction)

        return self._execute_write(operation, audit_context=audit_context)

    def append_transaction(
        self,
        book_code: str,
        transaction: JournalTransaction,
        *,
        audit_context: AuditContext,
    ) -> StoreWriteReceipt:
        """Append a posted transaction to an existing book."""
        if transaction.state is not TransactionState.POSTED:
            msg = "Only posted transactions can be appended to the ledger store"
            raise ValueError(msg)
        validate_transaction_balance(transaction)
        with self._writer_lock:
            known_account_codes = {
                cast("str", row[0])
                for row in _fetchall(
                    self._writer_connection,
                    "SELECT code FROM accounts WHERE book_code = ? ORDER BY code",
                    (book_code,),
                )
            }
            if not known_account_codes:
                msg = f"Unknown book: {book_code}"
                raise KeyError(msg)
            for entry in transaction.entries:
                if entry.account_code not in known_account_codes:
                    msg = f"Unknown account code for book {book_code}: {entry.account_code}"
                    raise ValueError(msg)
            with self._capture_write_session() as session, self._audit_context(audit_context):
                with self._writer_connection:
                    self._insert_transaction_rows(book_code, transaction)
                return _build_write_receipt(
                    session,
                    data_version=self._writer_connection.data_version(),
                    last_wal_commit=self._last_wal_commit_snapshot(),
                )

    def _insert_transaction_rows(self, book_code: str, transaction: JournalTransaction) -> None:
        """Insert one transaction row and its entry rows."""
        self._writer_connection.execute(
            """
            INSERT INTO transactions(
                book_code,
                reference,
                posted_at,
                description,
                state,
                period_fiscal_year,
                period_quarter,
                period_month,
                reversal_of
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                book_code,
                transaction.reference,
                transaction.posted_at.isoformat(),
                transaction.description,
                transaction.state.value,
                None if transaction.period is None else transaction.period.fiscal_year,
                None if transaction.period is None else transaction.period.quarter,
                None if transaction.period is None else transaction.period.month,
                transaction.reversal_of,
            ),
        )
        for line_no, entry in enumerate(transaction.entries):
            self._writer_connection.execute(
                """
                INSERT INTO entries(
                    book_code,
                    transaction_reference,
                    line_no,
                    account_code,
                    side,
                    amount,
                    currency,
                    description,
                    tax_rate
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    book_code,
                    transaction.reference,
                    line_no,
                    entry.account_code,
                    entry.side.value,
                    format(entry.decimal_value, "f"),
                    entry.currency,
                    entry.description,
                    None if entry.tax_rate is None else format(entry.tax_rate, "f"),
                ),
            )

    def list_book_codes(self) -> tuple[str, ...]:
        """Return all known book codes in deterministic order."""
        with self._borrow_reader() as handle:
            return tuple(
                cast("str", row[0])
                for row in _fetchall(
                    handle.connection,
                    "SELECT book_code FROM books ORDER BY book_code",
                )
            )

    def load_book(self, book_code: str) -> Book:
        """Load a complete immutable book aggregate from SQLite."""
        with self._borrow_reader() as handle:
            return _load_book_from_connection(handle.connection, book_code)

    def export_book_payload(self, book_code: str) -> dict[str, object]:
        """Return a deterministic mapping for a stored book."""
        return book_to_mapping(self.load_book(book_code))

    def iter_audit_log(self, *, limit: int | None = None) -> tuple[AuditLogRecord, ...]:
        """Return audit log rows ordered by sequence number."""
        sql = (
            "SELECT seq, table_name, operation, row_pk, actor, reason, session_id, "
            "monotonic_ms, row_signature, row_payload "
            "FROM audit_log ORDER BY seq"
        )
        bindings: tuple[SQLiteBinding, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            bindings = (limit,)
        with self._borrow_reader() as handle:
            return _build_audit_log_records(_fetchall(handle.connection, sql, bindings))

    def append_legislative_result(
        self,
        book_code: str,
        transaction_reference: str,
        result: LegislativeValidationResult,
        *,
        audit_context: AuditContext,
    ) -> StoreWriteReceipt:
        """Append a post-commit legislative validation result to the audit trail."""
        payload_json = json.dumps(
            {
                "book_code": book_code,
                "transaction_reference": transaction_reference,
                "pack_code": result.pack_code,
                "issues": [
                    {
                        "code": issue.code,
                        "message": issue.message,
                        "entry_index": issue.entry_index,
                    }
                    for issue in result.issues
                ],
            },
            separators=(",", ":"),
            sort_keys=True,
        )

        def operation() -> None:
            self._writer_connection.execute(
                """
                INSERT INTO audit_log(
                    table_name,
                    operation,
                    row_pk,
                    actor,
                    reason,
                    session_id,
                    monotonic_ms,
                    row_signature,
                    row_payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legislative_validation",
                    "RESULT",
                    f"{book_code}:{transaction_reference}",
                    audit_context.actor,
                    audit_context.reason,
                    audit_context.session_id,
                    time.monotonic_ns() // 1_000_000,
                    blake2b(payload_json.encode("utf-8"), digest_size=16).hexdigest(),
                    payload_json,
                ),
            )

        return self._execute_write(operation, audit_context=audit_context)

    def debug_snapshot(self) -> StoreDebugSnapshot:
        """Return a non-invasive snapshot of store counters and APSW telemetry."""
        with self._borrow_all_readers() as reader_handles:
            count_connection = reader_handles[0].connection
            reader_snapshots = tuple(
                _build_connection_debug_snapshot(handle.label, handle.connection)
                for handle in reader_handles
            )
            book_count = _fetch_scalar_int(count_connection, "SELECT COUNT(*) FROM books")
            transaction_count = _fetch_scalar_int(
                count_connection,
                "SELECT COUNT(*) FROM transactions",
            )
            entry_count = _fetch_scalar_int(count_connection, "SELECT COUNT(*) FROM entries")
            audit_row_count = _fetch_scalar_int(
                count_connection,
                "SELECT COUNT(*) FROM audit_log",
            )
        with self._writer_lock:
            writer_snapshot = _build_connection_debug_snapshot("writer", self._writer_connection)
            reserve_bytes = self._writer_connection.reserve_bytes()
        with self._telemetry_lock:
            last_wal_commit = self._last_wal_commit
            recent_trace_events = tuple(self._trace_events)
            recent_profile_events = tuple(self._profile_events)
        return StoreDebugSnapshot(
            database_path=self.database_path,
            reserve_bytes=reserve_bytes,
            book_count=book_count,
            transaction_count=transaction_count,
            entry_count=entry_count,
            audit_row_count=audit_row_count,
            writer=writer_snapshot,
            readers=reader_snapshots,
            last_wal_commit=last_wal_commit,
            recent_trace_events=recent_trace_events,
            recent_profile_events=recent_profile_events,
        )

    def create_snapshot(
        self,
        output_path: Path | str,
        *,
        compress: bool = True,
    ) -> DatabaseSnapshot:
        """Create a WAL-consistent database snapshot, optionally compressed with zstd."""
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._writer_lock:
            wal_frames, checkpointed_frames = self._writer_connection.wal_checkpoint(
                mode=apsw.SQLITE_CHECKPOINT_TRUNCATE,
            )
            temp_path = destination.with_suffix(".sqlite3") if compress else destination

            destination_connection = apsw.Connection(str(temp_path), vfs=self._config.vfs_name)
            try:
                backup = destination_connection.backup("main", self._writer_connection, "main")
                try:
                    while not backup.step(256):
                        continue
                finally:
                    backup.finish()
            finally:
                destination_connection.close()

        if compress:
            raw_bytes = temp_path.read_bytes()
            compressed_bytes = zstd.compress(raw_bytes)
            destination.write_bytes(compressed_bytes)
            temp_path.unlink()
            bytes_written = len(compressed_bytes)
        else:
            bytes_written = temp_path.stat().st_size

        return DatabaseSnapshot(
            output_path=destination,
            compressed=compress,
            wal_frames=wal_frames,
            checkpointed_frames=checkpointed_frames,
            bytes_written=bytes_written,
        )

    async def open_async_reader(self) -> AsyncLedgerReader:
        """Open an APSW async read-only facade using the current persistence config."""
        return await AsyncLedgerReader.open(self._config)
