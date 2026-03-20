"""Hypothesis strategies for FinestVX persistence and legislation configuration tests."""

from __future__ import annotations

from hypothesis import event
from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy

__all__ = [
    "invalid_reserve_bytes",
    "invalid_tax_years",
    "valid_reserve_bytes",
    "valid_tax_years",
]

_RESERVE_BYTES_MIN = 0
_RESERVE_BYTES_MAX = 255
_TAX_YEAR_MIN = 1
_TAX_YEAR_MAX = 9999


def valid_reserve_bytes() -> SearchStrategy[int]:
    """Generate integers in the valid SQLite page-reservation range [0, 255].

    Events emitted:
    - strategy=reserve_bytes_boundary: value is 0 or 255.
    - strategy=reserve_bytes_interior: value is strictly between 0 and 255.
    """
    return st.integers(min_value=_RESERVE_BYTES_MIN, max_value=_RESERVE_BYTES_MAX).map(
        _track_reserve_bytes_in_range
    )


def _track_reserve_bytes_in_range(value: int) -> int:
    if value in (_RESERVE_BYTES_MIN, _RESERVE_BYTES_MAX):
        event("strategy=reserve_bytes_boundary")
    else:
        event("strategy=reserve_bytes_interior")
    return value


def invalid_reserve_bytes() -> SearchStrategy[int]:
    """Generate integers strictly outside the valid [0, 255] range.

    Events emitted:
    - strategy=reserve_bytes_negative: value is less than 0.
    - strategy=reserve_bytes_overflow: value is greater than 255.
    """
    negative = st.integers(min_value=-512, max_value=-1).map(
        _track_reserve_bytes_negative
    )
    overflow = st.integers(min_value=256, max_value=512).map(
        _track_reserve_bytes_overflow
    )
    return st.one_of(negative, overflow)


def _track_reserve_bytes_negative(value: int) -> int:
    event("strategy=reserve_bytes_negative")
    return value


def _track_reserve_bytes_overflow(value: int) -> int:
    event("strategy=reserve_bytes_overflow")
    return value


def valid_tax_years() -> SearchStrategy[int]:
    """Generate tax-year integers within the valid [1, 9999] range.

    Events emitted:
    - strategy=tax_year_boundary: value is 1 or 9999.
    - strategy=tax_year_modern: value is a recent year (2000-2099).
    - strategy=tax_year_historic: value is outside 2000-2099.
    """
    return st.integers(min_value=_TAX_YEAR_MIN, max_value=_TAX_YEAR_MAX).map(
        _track_tax_year_in_range
    )


def _track_tax_year_in_range(value: int) -> int:
    if value in (_TAX_YEAR_MIN, _TAX_YEAR_MAX):
        event("strategy=tax_year_boundary")
    elif 2000 <= value <= 2099:
        event("strategy=tax_year_modern")
    else:
        event("strategy=tax_year_historic")
    return value


def invalid_tax_years() -> SearchStrategy[int]:
    """Generate integers strictly outside the valid [1, 9999] range.

    Events emitted:
    - strategy=tax_year_zero_or_negative: value is <= 0.
    - strategy=tax_year_overflow: value is >= 10000.
    """
    zero_or_neg = st.integers(min_value=-9999, max_value=0).map(
        _track_tax_year_zero_or_negative
    )
    overflow = st.integers(min_value=10000, max_value=20000).map(
        _track_tax_year_overflow
    )
    return st.one_of(zero_or_neg, overflow)


def _track_tax_year_zero_or_negative(value: int) -> int:
    event("strategy=tax_year_zero_or_negative")
    return value


def _track_tax_year_overflow(value: int) -> int:
    event("strategy=tax_year_overflow")
    return value
