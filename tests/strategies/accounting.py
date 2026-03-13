"""Hypothesis strategies for FinestVX accounting-domain tests."""

from __future__ import annotations

from decimal import Decimal

from ftllexengine import FluentNumber
from hypothesis import event
from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy

__all__ = [
    "currencies",
    "fluent_amounts",
    "transaction_references",
]


def currencies() -> SearchStrategy[str]:
    """Generate ISO 4217 currency codes used in test scenarios.

    Events emitted:
    - strategy=currency_{code}: which currency was chosen.
    """
    return st.sampled_from(("EUR", "USD")).map(_track_currency)


def _track_currency(code: str) -> str:
    event(f"strategy=currency_{code}")
    return code


def transaction_references() -> SearchStrategy[str]:
    """Generate valid transaction reference strings.

    Events emitted:
    - strategy=reference: reference was generated (length emitted separately).
    """
    return st.text(
        alphabet=st.characters(min_codepoint=48, max_codepoint=90),
        min_size=4,
        max_size=12,
    ).filter(lambda value: value.strip() != "").map(_track_reference)


def _track_reference(ref: str) -> str:
    event(f"strategy=reference_len_{len(ref)}")
    return ref


def _build_fluent_number(value: Decimal) -> FluentNumber:
    """Create a ``FluentNumber`` preserving decimal scale for tests."""
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        msg = "decimal exponent must be int for finite decimal values"
        raise TypeError(msg)
    precision = max(-exponent, 0)
    event(f"strategy=amount_precision_{precision}")
    return FluentNumber(value=value, formatted=format(value, "f"), precision=precision)


def fluent_amounts() -> SearchStrategy[FluentNumber]:
    """Generate non-negative ``FluentNumber`` values for ledger entries.

    Events emitted:
    - strategy=amount_precision_{n}: decimal precision of the generated amount.
    """
    return st.decimals(
        min_value=Decimal("0.01"),
        max_value=Decimal("999999.99"),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    ).map(_build_fluent_number)
