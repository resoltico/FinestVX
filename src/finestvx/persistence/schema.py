# mypy: disable-error-code=misc
"""SQLite schema helpers for the FinestVX append-only ledger store."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .sql import render_sql

if TYPE_CHECKING:
    from collections.abc import Iterable

    import apsw

__all__ = [
    "CORE_TABLES",
    "SCHEMA_VERSION",
    "apply_sqlite_pragmas",
    "install_schema",
]

SCHEMA_VERSION = 1
CORE_TABLES = (
    "books",
    "accounts",
    "periods",
    "transactions",
    "entries",
)

_SCHEMA_SQL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS books (
        book_code TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        base_currency TEXT NOT NULL,
        fiscal_start_month INTEGER NOT NULL CHECK (fiscal_start_month BETWEEN 1 AND 12),
        legislative_pack TEXT NOT NULL
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS accounts (
        book_code TEXT NOT NULL,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        normal_side TEXT NOT NULL CHECK (normal_side IN ('Dr', 'Cr')),
        currency TEXT NOT NULL,
        parent_code TEXT,
        allow_posting INTEGER NOT NULL CHECK (allow_posting IN (0, 1)),
        active INTEGER NOT NULL CHECK (active IN (0, 1)),
        PRIMARY KEY (book_code, code),
        FOREIGN KEY (book_code) REFERENCES books(book_code),
        FOREIGN KEY (book_code, parent_code) REFERENCES accounts(book_code, code)
            DEFERRABLE INITIALLY DEFERRED
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS periods (
        book_code TEXT NOT NULL,
        fiscal_year INTEGER NOT NULL,
        quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
        month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('open', 'closed', 'locked')),
        PRIMARY KEY (book_code, fiscal_year, quarter, month),
        FOREIGN KEY (book_code) REFERENCES books(book_code)
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS transactions (
        book_code TEXT NOT NULL,
        reference TEXT NOT NULL,
        posted_at TEXT NOT NULL,
        description TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('draft', 'posted', 'reversed')),
        period_fiscal_year INTEGER,
        period_quarter INTEGER,
        period_month INTEGER,
        reversal_of TEXT,
        PRIMARY KEY (book_code, reference),
        FOREIGN KEY (book_code) REFERENCES books(book_code),
        CHECK (
            (period_fiscal_year IS NULL AND period_quarter IS NULL AND period_month IS NULL)
            OR
            (
                period_fiscal_year IS NOT NULL
                AND period_quarter IS NOT NULL
                AND period_month IS NOT NULL
            )
        )
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS entries (
        book_code TEXT NOT NULL,
        transaction_reference TEXT NOT NULL,
        line_no INTEGER NOT NULL CHECK (line_no >= 0),
        account_code TEXT NOT NULL,
        side TEXT NOT NULL CHECK (side IN ('Dr', 'Cr')),
        amount TEXT NOT NULL CHECK (amount <> '' AND amount NOT LIKE '-%'),
        currency TEXT NOT NULL,
        description TEXT,
        tax_rate TEXT CHECK (tax_rate IS NULL OR tax_rate NOT LIKE '-%'),
        PRIMARY KEY (book_code, transaction_reference, line_no),
        FOREIGN KEY (book_code, transaction_reference)
            REFERENCES transactions(book_code, reference),
        FOREIGN KEY (book_code, account_code)
            REFERENCES accounts(book_code, code)
    ) STRICT
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        seq INTEGER PRIMARY KEY,
        table_name TEXT NOT NULL,
        operation TEXT NOT NULL,
        row_pk TEXT NOT NULL,
        actor TEXT NOT NULL,
        reason TEXT NOT NULL,
        session_id TEXT,
        monotonic_ms INTEGER NOT NULL,
        row_signature TEXT NOT NULL,
        row_payload TEXT NOT NULL
    ) STRICT
    """,
    "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', '1')",
)


_APPEND_ONLY_TRIGGERS: tuple[str, ...] = tuple(
    statement
    for table_name in CORE_TABLES
    for statement in (
        render_sql(
            t"""
            CREATE TRIGGER IF NOT EXISTS {f"{table_name}_no_update":identifier}
            BEFORE UPDATE ON {table_name:identifier}
            BEGIN
                SELECT RAISE(ABORT, {f"append-only table: {table_name}":literal});
            END
            """
        ),
        render_sql(
            t"""
            CREATE TRIGGER IF NOT EXISTS {f"{table_name}_no_delete":identifier}
            BEFORE DELETE ON {table_name:identifier}
            BEGIN
                SELECT RAISE(ABORT, {f"append-only table: {table_name}":literal});
            END
            """
        ),
    )
)


_AUDIT_TRIGGERS: tuple[str, ...] = (
    """
    CREATE TRIGGER IF NOT EXISTS books_audit_insert
    AFTER INSERT ON books
    BEGIN
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
        VALUES (
            'books',
            'INSERT',
            NEW.book_code,
            audit_actor(),
            audit_reason(),
            audit_session_id(),
            monotonic_ms(),
            blake2_hex(json_object(
                'book_code', NEW.book_code,
                'name', NEW.name,
                'base_currency', NEW.base_currency,
                'fiscal_start_month', NEW.fiscal_start_month,
                'legislative_pack', NEW.legislative_pack
            )),
            json_object(
                'book_code', NEW.book_code,
                'name', NEW.name,
                'base_currency', NEW.base_currency,
                'fiscal_start_month', NEW.fiscal_start_month,
                'legislative_pack', NEW.legislative_pack
            )
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS accounts_audit_insert
    AFTER INSERT ON accounts
    BEGIN
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
        VALUES (
            'accounts',
            'INSERT',
            printf('%s:%s', NEW.book_code, NEW.code),
            audit_actor(),
            audit_reason(),
            audit_session_id(),
            monotonic_ms(),
            blake2_hex(json_object(
                'book_code', NEW.book_code,
                'code', NEW.code,
                'name', NEW.name,
                'normal_side', NEW.normal_side,
                'currency', NEW.currency,
                'parent_code', NEW.parent_code,
                'allow_posting', NEW.allow_posting,
                'active', NEW.active
            )),
            json_object(
                'book_code', NEW.book_code,
                'code', NEW.code,
                'name', NEW.name,
                'normal_side', NEW.normal_side,
                'currency', NEW.currency,
                'parent_code', NEW.parent_code,
                'allow_posting', NEW.allow_posting,
                'active', NEW.active
            )
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS periods_audit_insert
    AFTER INSERT ON periods
    BEGIN
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
        VALUES (
            'periods',
            'INSERT',
            printf('%s:%d:%d:%d', NEW.book_code, NEW.fiscal_year, NEW.quarter, NEW.month),
            audit_actor(),
            audit_reason(),
            audit_session_id(),
            monotonic_ms(),
            blake2_hex(json_object(
                'book_code', NEW.book_code,
                'fiscal_year', NEW.fiscal_year,
                'quarter', NEW.quarter,
                'month', NEW.month,
                'start_date', NEW.start_date,
                'end_date', NEW.end_date,
                'state', NEW.state
            )),
            json_object(
                'book_code', NEW.book_code,
                'fiscal_year', NEW.fiscal_year,
                'quarter', NEW.quarter,
                'month', NEW.month,
                'start_date', NEW.start_date,
                'end_date', NEW.end_date,
                'state', NEW.state
            )
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS transactions_audit_insert
    AFTER INSERT ON transactions
    BEGIN
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
        VALUES (
            'transactions',
            'INSERT',
            printf('%s:%s', NEW.book_code, NEW.reference),
            audit_actor(),
            audit_reason(),
            audit_session_id(),
            monotonic_ms(),
            blake2_hex(json_object(
                'book_code', NEW.book_code,
                'reference', NEW.reference,
                'posted_at', NEW.posted_at,
                'description', NEW.description,
                'state', NEW.state,
                'period_fiscal_year', NEW.period_fiscal_year,
                'period_quarter', NEW.period_quarter,
                'period_month', NEW.period_month,
                'reversal_of', NEW.reversal_of
            )),
            json_object(
                'book_code', NEW.book_code,
                'reference', NEW.reference,
                'posted_at', NEW.posted_at,
                'description', NEW.description,
                'state', NEW.state,
                'period_fiscal_year', NEW.period_fiscal_year,
                'period_quarter', NEW.period_quarter,
                'period_month', NEW.period_month,
                'reversal_of', NEW.reversal_of
            )
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS entries_audit_insert
    AFTER INSERT ON entries
    BEGIN
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
        VALUES (
            'entries',
            'INSERT',
            printf('%s:%s:%d', NEW.book_code, NEW.transaction_reference, NEW.line_no),
            audit_actor(),
            audit_reason(),
            audit_session_id(),
            monotonic_ms(),
            blake2_hex(json_object(
                'book_code', NEW.book_code,
                'transaction_reference', NEW.transaction_reference,
                'line_no', NEW.line_no,
                'account_code', NEW.account_code,
                'side', NEW.side,
                'amount', NEW.amount,
                'currency', NEW.currency,
                'description', NEW.description,
                'tax_rate', NEW.tax_rate
            )),
            json_object(
                'book_code', NEW.book_code,
                'transaction_reference', NEW.transaction_reference,
                'line_no', NEW.line_no,
                'account_code', NEW.account_code,
                'side', NEW.side,
                'amount', NEW.amount,
                'currency', NEW.currency,
                'description', NEW.description,
                'tax_rate', NEW.tax_rate
            )
        );
    END
    """,
)


def _execute_batch(connection: apsw.Connection, statements: Iterable[str]) -> None:
    """Execute a batch of SQL statements."""
    for statement in statements:
        connection.execute(statement)


def apply_sqlite_pragmas(connection: apsw.Connection, *, wal_auto_checkpoint: int) -> None:
    """Apply the mandatory SQLite pragmas for FinestVX."""
    connection.pragma("journal_mode", "WAL")
    connection.pragma("foreign_keys", 1)
    connection.pragma("synchronous", "FULL")
    connection.pragma("wal_autocheckpoint", wal_auto_checkpoint)


def install_schema(connection: apsw.Connection) -> None:
    """Install the FinestVX ledger schema, triggers, and metadata."""
    with connection:
        _execute_batch(connection, _SCHEMA_SQL)
        _execute_batch(connection, _APPEND_ONLY_TRIGGERS)
        _execute_batch(connection, _AUDIT_TRIGGERS)
