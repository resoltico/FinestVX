"""Shared primitive validators for FinestVX core domain models.

These functions are used by multiple modules within the finestvx.core and
finestvx.legislation packages. Keeping them in one place eliminates duplication
while preserving the principle of locality — only the packages that own domain
construction call these helpers.

This module is private (underscore prefix) and not exported from the package's
public API.
"""

from __future__ import annotations

__all__: list[str] = []


def require_non_empty_text(value: object, field_name: str) -> str:
    """Validate and normalize a required text field.

    Args:
        value: Candidate text value.
        field_name: Field name for diagnostics.

    Returns:
        Stripped text value.

    Raises:
        TypeError: If the value is not a string.
        ValueError: If the value is empty after trimming.
    """
    if not isinstance(value, str):
        msg = f"{field_name} must be str, got {type(value).__name__}"
        raise TypeError(msg)
    normalized = value.strip()
    if not normalized:
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)
    return normalized


def normalize_optional_text(value: object, field_name: str) -> str | None:
    """Normalize an optional text field.

    Args:
        value: Candidate text value (may be None).
        field_name: Field name for diagnostics.

    Returns:
        Stripped text value or ``None``.

    Raises:
        TypeError: If the value is not a string and not None.
        ValueError: If the value is non-None but empty after trimming.
    """
    if value is None:
        return None
    return require_non_empty_text(value, field_name)
