"""APSW-backed append-only ledger store for FinestVX."""

from __future__ import annotations

import json
import time
from collections.abc import Buffer
from compression import zstd
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import blake2b
from pathlib import Path
from typing import TYPE_CHECKING, cast

import apsw

from finestvx.core.enums import TransactionState
from finestvx.core.serialization import book_from_mapping, book_to_mapping
from finestvx.core.validation import validate_chart_of_accounts, validate_transaction_balance
from finestvx.persistence.config import DatabaseSnapshot
from finestvx.persistence.schema import apply_sqlite_pragmas, install_schema

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from finestvx.core.models import Book, JournalTransaction
    from finestvx.legislation.protocols import LegislativeValidationResult
    from finestvx.persistence.config import AuditContext, PersistenceConfig

__all__ = [
    "AuditLogRecord",
    "SqliteLedgerStore",
    "StoreDebugSnapshot",
]

type SQLiteBinding = int | float | Buffer | str | None
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
class StoreDebugSnapshot:
    """Non-invasive debug snapshot for the APSW-backed ledger store."""

    database_path: Path
    book_count: int
    transaction_count: int
    entry_count: int
    audit_row_count: int


@dataclass(slots=True)
class _AuditState:
    """Mutable per-connection audit context exposed to SQLite scalar functions."""

    actor: str = "system"
    reason: str = "schema/bootstrap"
    session_id: str | None = None


class SqliteLedgerStore:
    """SQLite WAL store with append-only rules and SQL-triggered audit logging."""

    __slots__ = ("_audit_state", "_config", "_connection")

    def __init__(self, config: PersistenceConfig) -> None:
        """Open the SQLite database, register functions, and install schema."""
        self._config = config
        database_path = Path(self._config.database_path)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._audit_state = _AuditState()
        self._connection = apsw.Connection(str(database_path))
        self._connection.transaction_mode = self._config.transaction_mode
        self._connection.setbusytimeout(self._config.busy_timeout_ms)
        self._register_sql_functions()
        apply_sqlite_pragmas(
            self._connection,
            wal_auto_checkpoint=self._config.wal_auto_checkpoint,
        )
        install_schema(self._connection)

    @property
    def database_path(self) -> Path:
        """Return the on-disk SQLite database path."""
        return Path(self._config.database_path)

    def close(self) -> None:
        """Close the underlying APSW connection."""
        self._connection.close()

    def _fetchall(
        self,
        sql: str,
        bindings: tuple[SQLiteBinding, ...] = (),
    ) -> list[tuple[SQLiteBinding, ...]]:
        """Execute a query and return all rows eagerly."""
        cursor = self._connection.cursor()
        cursor.execute(sql, bindings)
        return cursor.fetchall()

    def _fetch_scalar_int(
        self,
        sql: str,
        bindings: tuple[SQLiteBinding, ...] = (),
    ) -> int:
        """Execute a scalar count query and normalize the integer result."""
        row = self._connection.execute(sql, bindings).fetchone()
        if row is None or isinstance(row[0], bool) or not isinstance(row[0], int):
            msg = f"Expected scalar integer result for SQL query: {sql}"
            raise TypeError(msg)
        return cast("int", row[0])

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

        self._connection.create_scalar_function(
            "blake2_hex",
            blake2_hex,
            1,
            deterministic=True,
        )
        self._connection.create_scalar_function(
            "audit_actor",
            audit_actor,
            0,
        )
        self._connection.create_scalar_function(
            "audit_reason",
            audit_reason,
            0,
        )
        self._connection.create_scalar_function(
            "audit_session_id",
            audit_session_id,
            0,
        )
        self._connection.create_scalar_function(
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

    def create_book(self, book: Book, *, audit_context: AuditContext) -> None:
        """Persist a new book and its immutable bootstrap data."""
        validate_chart_of_accounts(book.accounts)
        with self._audit_context(audit_context), self._connection:
            self._connection.execute(
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
                self._connection.execute(
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
                self._connection.execute(
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

    def append_transaction(
        self,
        book_code: str,
        transaction: JournalTransaction,
        *,
        audit_context: AuditContext,
    ) -> None:
        """Append a posted transaction to an existing book."""
        if transaction.state is not TransactionState.POSTED:
            msg = "Only posted transactions can be appended to the ledger store"
            raise ValueError(msg)
        validate_transaction_balance(transaction)
        known_account_codes = {
            row[0]
            for row in self._fetchall(
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
        with self._audit_context(audit_context), self._connection:
            self._insert_transaction_rows(book_code, transaction)

    def _insert_transaction_rows(self, book_code: str, transaction: JournalTransaction) -> None:
        """Insert one transaction row and its entry rows."""
        self._connection.execute(
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
            self._connection.execute(
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
        return tuple(
            cast("str", row[0])
            for row in self._fetchall(
                "SELECT book_code FROM books ORDER BY book_code"
            )
        )

    def load_book(self, book_code: str) -> Book:
        """Load a complete immutable book aggregate from SQLite."""
        book_row = self._connection.execute(
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
            for row in self._fetchall(
                """
                SELECT code, name, normal_side, currency, parent_code, allow_posting, active
                FROM accounts
                WHERE book_code = ?
                ORDER BY code
                """,
                (book_code,),
            )
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
            for row in self._fetchall(
                """
                SELECT fiscal_year, quarter, month, start_date, end_date, state
                FROM periods
                WHERE book_code = ?
                ORDER BY start_date, end_date, fiscal_year, quarter, month
                """,
                (book_code,),
            )
        ]

        transactions: list[dict[str, object]] = []
        for tx_row in self._fetchall(
            """
            SELECT reference, posted_at, description, state, period_fiscal_year, period_quarter,
                   period_month, reversal_of
            FROM transactions
            WHERE book_code = ?
            ORDER BY posted_at, reference
            """,
            (book_code,),
        ):
            entries = [
                {
                    "account_code": entry_row[0],
                    "side": entry_row[1],
                    "amount": entry_row[2],
                    "currency": entry_row[3],
                    "description": entry_row[4],
                    "tax_rate": entry_row[5],
                }
                for entry_row in self._fetchall(
                    """
                    SELECT account_code, side, amount, currency, description, tax_rate
                    FROM entries
                    WHERE book_code = ? AND transaction_reference = ?
                    ORDER BY line_no
                    """,
                    (book_code, tx_row[0]),
                )
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

        payload = {
            "code": book_row[0],
            "name": book_row[1],
            "base_currency": book_row[2],
            "fiscal_calendar": {"start_month": book_row[3]},
            "legislative_pack": book_row[4],
            "accounts": accounts,
            "periods": periods,
            "transactions": transactions,
        }
        return book_from_mapping(payload)

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
        return tuple(
            AuditLogRecord(*cast("AuditLogRow", row))
            for row in self._fetchall(sql, bindings)
        )

    def execute(self, sql: str, bindings: Iterable[SQLiteBinding] = ()) -> apsw.Cursor:
        """Execute raw SQL against the underlying connection."""
        return self._connection.execute(sql, tuple(bindings))

    def append_legislative_result(
        self,
        book_code: str,
        transaction_reference: str,
        result: LegislativeValidationResult,
        *,
        audit_context: AuditContext,
    ) -> None:
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
        with self._audit_context(audit_context), self._connection:
            self._connection.execute(
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

    def debug_snapshot(self) -> StoreDebugSnapshot:
        """Return a non-invasive snapshot of store-level counters."""
        return StoreDebugSnapshot(
            database_path=self.database_path,
            book_count=self._fetch_scalar_int("SELECT COUNT(*) FROM books"),
            transaction_count=self._fetch_scalar_int("SELECT COUNT(*) FROM transactions"),
            entry_count=self._fetch_scalar_int("SELECT COUNT(*) FROM entries"),
            audit_row_count=self._fetch_scalar_int("SELECT COUNT(*) FROM audit_log"),
        )

    def _wal_checkpoint_stats(self) -> tuple[int, int]:
        """Return WAL checkpoint statistics as a normalized integer pair."""
        # APSW exposes checkpoint counts as a runtime tuple even though its stubs are sparse.
        wal_frames, checkpointed_frames = self._connection.wal_checkpoint(
            mode=apsw.SQLITE_CHECKPOINT_TRUNCATE
        )
        return (wal_frames, checkpointed_frames)

    def create_snapshot(
        self,
        output_path: Path | str,
        *,
        compress: bool = True,
    ) -> DatabaseSnapshot:
        """Create a WAL-consistent database snapshot, optionally compressed with zstd."""
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        wal_frames, checkpointed_frames = self._wal_checkpoint_stats()
        temp_path = destination.with_suffix(".sqlite3") if compress else destination

        destination_connection = apsw.Connection(str(temp_path))
        try:
            backup = destination_connection.backup("main", self._connection, "main")
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
