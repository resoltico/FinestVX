"""Shared primitive validators for FinestVX core domain models.

These functions are used by multiple modules within the finestvx.core and
finestvx.legislation packages. Keeping them in one place eliminates duplication
while preserving the principle of locality — only the packages that own domain
construction call these helpers.

This module is private (underscore prefix) and not exported from the package's
public API.
"""

from __future__ import annotations

from collections.abc import Sequence

from ftllexengine import require_non_empty_str

__all__: list[str] = []


def _coerce_tuple[T](value: object, field_name: str) -> tuple[T, ...]:
    """Accept any sequence input and normalize to immutable tuple storage.

    Args:
        value: Candidate sequence value (tuple, list, or any Sequence except str).
        field_name: Field name for diagnostics.

    Returns:
        Immutable tuple containing the original elements.

    Raises:
        TypeError: If the value is a string or a non-Sequence type.
    """
    if isinstance(value, tuple):
        return value
    if isinstance(value, Sequence) and not isinstance(value, str):
        return tuple(value)
    msg = f"{field_name} must be a sequence, got {type(value).__name__}"
    raise TypeError(msg)


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
    return require_non_empty_str(value, field_name)
