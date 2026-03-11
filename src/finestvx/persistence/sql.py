"""PEP 750 template-string helpers for safe SQLite SQL rendering."""

from __future__ import annotations

import re
from string.templatelib import Template

__all__ = [
    "quote_identifier",
    "quote_literal",
    "render_sql",
]

_SQLITE_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def quote_identifier(identifier: object) -> str:
    """Quote and validate a SQLite identifier."""
    if not isinstance(identifier, str):
        msg = f"SQLite identifier must be str, got {type(identifier).__name__}"
        raise TypeError(msg)
    if not _SQLITE_IDENTIFIER_RE.fullmatch(identifier):
        msg = f"Invalid SQLite identifier: {identifier!r}"
        raise ValueError(msg)
    return f'"{identifier}"'


def quote_literal(value: object) -> str:
    """Quote a SQL literal for static schema rendering."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        msg = "SQLite literal values must not be bool"
        raise TypeError(msg)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    msg = f"Unsupported SQLite literal type: {type(value).__name__}"
    raise TypeError(msg)


def render_sql(template: Template) -> str:
    """Render a template string into validated SQL text."""
    parts: list[str] = []
    for item in template:
        if isinstance(item, str):
            parts.append(item)
            continue
        if item.conversion not in (None, ""):
            msg = f"Unsupported SQL template conversion: {item.conversion!r}"
            raise ValueError(msg)
        match item.format_spec:
            case "identifier":
                parts.append(quote_identifier(item.value))
            case "literal":
                parts.append(quote_literal(item.value))
            case "raw":
                if not isinstance(item.value, str):
                    msg = f"Raw SQL segments must be str, got {type(item.value).__name__}"
                    raise TypeError(msg)
                parts.append(item.value)
            case _:
                msg = f"Unsupported SQL template format spec: {item.format_spec!r}"
                raise ValueError(msg)
    return "".join(parts)
