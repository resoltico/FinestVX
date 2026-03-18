"""Shared primitive validators for FinestVX core domain models.

This module is private (underscore prefix) and not exported from the package's
public API.
"""

from __future__ import annotations

from ftllexengine import require_non_empty_str

__all__: list[str] = []


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
