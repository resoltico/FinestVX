# mypy: disable-error-code=misc
"""Tests for FinestVX SQL template rendering helpers."""

from __future__ import annotations

from typing import Any, cast

import pytest

from finestvx.persistence.sql import quote_identifier, quote_literal, render_sql


class TestPersistenceSqlTemplates:
    """Template-string rendering checks for schema SQL generation."""

    def test_render_sql_supports_identifier_and_literal_interpolations(self) -> None:
        """Validated identifiers and string literals render into static SQL safely."""
        table_name = "books"
        error_message = "append-only table: books"

        sql = render_sql(
            t"""
            CREATE TRIGGER {f"{table_name}_no_update":identifier}
            BEFORE UPDATE ON {table_name:identifier}
            BEGIN
                SELECT RAISE(ABORT, {error_message:literal});
            END
            """
        )

        assert '"books_no_update"' in sql
        assert '"books"' in sql
        assert "'append-only table: books'" in sql
        assert quote_identifier("entries") == '"entries"'
        assert quote_literal("demo's") == "'demo''s'"
        assert quote_literal(3) == "3"

    def test_render_sql_rejects_invalid_identifier_literal_and_format_spec(self) -> None:
        """Invalid template payloads fail fast before any SQL reaches SQLite."""
        invalid_identifier = "books; DROP TABLE books"

        with pytest.raises(ValueError, match="Invalid SQLite identifier"):
            render_sql(t"SELECT * FROM {invalid_identifier:identifier}")
        with pytest.raises(TypeError, match="SQLite identifier must be str"):
            quote_identifier(cast("Any", 123))
        with pytest.raises(TypeError, match="SQLite literal values must not be bool"):
            quote_literal(True)
        with pytest.raises(ValueError, match="Unsupported SQL template format spec"):
            render_sql(t"SELECT {invalid_identifier:unknown}")
