"""Hypothesis strategies for FinestVX accounting-domain tests."""

from __future__ import annotations

from decimal import Decimal

from ftllexengine import FluentNumber, make_fluent_number
from hypothesis import event
from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy

__all__ = [
    "currencies",
    "fluent_amounts",
    "optional_descriptions",
    "tax_rates_in_range",
    "tax_rates_out_of_range",
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
    """Create a canonical ``FluentNumber`` while still emitting scale events."""
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        msg = "decimal exponent must be int for finite decimal values"
        raise TypeError(msg)
    precision = max(-exponent, 0)
    event(f"strategy=amount_precision_{precision}")
    return make_fluent_number(value)


def tax_rates_in_range() -> SearchStrategy[Decimal]:
    """Generate Decimal values within the inclusive [0, 1] tax-rate range.

    Events emitted:
    - strategy=tax_rate_boundary: value is exactly 0 or 1.
    - strategy=tax_rate_interior: value is strictly between 0 and 1.
    """
    return st.decimals(
        min_value=Decimal(0),
        max_value=Decimal(1),
        places=4,
        allow_nan=False,
        allow_infinity=False,
    ).map(_track_tax_rate_in_range)


def _track_tax_rate_in_range(rate: Decimal) -> Decimal:
    if rate in (Decimal(0), Decimal(1)):
        event("strategy=tax_rate_boundary")
    else:
        event("strategy=tax_rate_interior")
    return rate


def tax_rates_out_of_range() -> SearchStrategy[Decimal]:
    """Generate finite Decimal values strictly outside the [0, 1] interval.

    Events emitted:
    - strategy=tax_rate_negative: value is less than 0.
    - strategy=tax_rate_above_one: value is greater than 1.
    """
    negative = st.decimals(
        min_value=Decimal(-1),
        max_value=Decimal("-0.0001"),
        places=4,
        allow_nan=False,
        allow_infinity=False,
    ).map(_track_tax_rate_negative)
    above_one = st.decimals(
        min_value=Decimal("1.0001"),
        max_value=Decimal(2),
        places=4,
        allow_nan=False,
        allow_infinity=False,
    ).map(_track_tax_rate_above_one)
    return st.one_of(negative, above_one)


def _track_tax_rate_negative(rate: Decimal) -> Decimal:
    event("strategy=tax_rate_negative")
    return rate


def _track_tax_rate_above_one(rate: Decimal) -> Decimal:
    event("strategy=tax_rate_above_one")
    return rate


def optional_descriptions() -> SearchStrategy[str | None]:
    """Generate optional description strings including None, padded, and plain.

    Events emitted:
    - strategy=description_none: value is None.
    - strategy=description_padded: value has leading/trailing whitespace.
    - strategy=description_plain: value is a plain non-blank string.
    """
    none_st = st.just(None).map(_track_description_none)
    padded_st = st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
        min_size=1,
        max_size=40,
    ).filter(lambda s: s.strip()).map(_track_description_padded)
    plain_st = st.text(
        alphabet=st.characters(min_codepoint=33, max_codepoint=126),
        min_size=1,
        max_size=40,
    ).map(_track_description_plain)
    return st.one_of(none_st, padded_st, plain_st)


def _track_description_none(value: None) -> None:
    event("strategy=description_none")
    return value


def _track_description_padded(value: str) -> str:
    event("strategy=description_padded")
    return f"  {value}  "


def _track_description_plain(value: str) -> str:
    event("strategy=description_plain")
    return value


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
