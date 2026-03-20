"""Runtime strategy metrics for FinestVX Hypothesis strategies.

Tracks expected events, strategy families, and intended weight distributions.
Activated during deep fuzz runs::

    ./scripts/fuzz_hypofuzz.sh --deep --metrics

Three constants are consumed by the metrics collection infrastructure:

- ``EXPECTED_EVENTS``: all strategy-level event strings emitted by
  ``tests/strategies/``.  Update when a new strategy variant is added.
- ``STRATEGY_CATEGORIES``: maps event prefix to a human-readable family name
  for grouped reporting.
- ``INTENDED_WEIGHTS``: expected per-variant fraction within each strategy
  family.  Used to detect skewed generation (threshold: 0.15 deviation).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Events emitted by tests/strategies/accounting.py
#
# currencies(): strategy=currency_{code} for each sampled currency
# transaction_references(): strategy=reference_len_{n} for n in 4..12
# fluent_amounts(): strategy=amount_precision_{n}; always 2 since places=2
# tax_rates_in_range(): strategy=tax_rate_boundary | strategy=tax_rate_interior
# tax_rates_out_of_range(): strategy=tax_rate_negative | strategy=tax_rate_above_one
# optional_descriptions(): strategy=description_none | _padded | _plain
# ---------------------------------------------------------------------------
#
# Events emitted by tests/strategies/config.py
#
# valid_reserve_bytes(): strategy=reserve_bytes_boundary | _interior
# invalid_reserve_bytes(): strategy=reserve_bytes_negative | _overflow
# valid_tax_years(): strategy=tax_year_boundary | _modern | _historic
# invalid_tax_years(): strategy=tax_year_zero_or_negative | _overflow
# ---------------------------------------------------------------------------

EXPECTED_EVENTS: frozenset[str] = frozenset(
    {
        # accounting.py — currencies
        "strategy=currency_EUR",
        "strategy=currency_USD",
        # accounting.py — transaction references
        *(f"strategy=reference_len_{n}" for n in range(4, 13)),
        # accounting.py — fluent amounts
        "strategy=amount_precision_2",
        # accounting.py — tax_rates_in_range
        "strategy=tax_rate_boundary",
        "strategy=tax_rate_interior",
        # accounting.py — tax_rates_out_of_range
        "strategy=tax_rate_negative",
        "strategy=tax_rate_above_one",
        # accounting.py — optional_descriptions
        "strategy=description_none",
        "strategy=description_padded",
        "strategy=description_plain",
        # config.py — valid_reserve_bytes
        "strategy=reserve_bytes_boundary",
        "strategy=reserve_bytes_interior",
        # config.py — invalid_reserve_bytes
        "strategy=reserve_bytes_negative",
        "strategy=reserve_bytes_overflow",
        # config.py — valid_tax_years
        "strategy=tax_year_boundary",
        "strategy=tax_year_modern",
        "strategy=tax_year_historic",
        # config.py — invalid_tax_years
        "strategy=tax_year_zero_or_negative",
        "strategy=tax_year_overflow",
    }
)

STRATEGY_CATEGORIES: dict[str, str] = {
    "strategy=currency_": "Currency selection",
    "strategy=reference_len_": "Transaction reference length",
    "strategy=amount_precision_": "Ledger amount decimal precision",
    "strategy=tax_rate_": "LedgerEntry tax rate range",
    "strategy=description_": "Optional description content",
    "strategy=reserve_bytes_": "SQLite page reservation bytes range",
    "strategy=tax_year_": "Legislative pack tax year range",
}

# Expected fraction of each variant within its family (must sum to ~1.0).
# A deviation > 0.15 from any entry signals a weight skew in generation.
INTENDED_WEIGHTS: dict[str, float] = {
    # currencies: uniform 50/50 across EUR and USD
    "strategy=currency_EUR": 0.5,
    "strategy=currency_USD": 0.5,
    # reference lengths: uniform across 4..12 (9 values)
    **{f"strategy=reference_len_{n}": 1 / 9 for n in range(4, 13)},
    # amounts: places=2 forces all generated values to have exactly 2 decimal places
    "strategy=amount_precision_2": 1.0,
    # tax rates in range: boundaries are rare (2 out of 10001 possible values)
    "strategy=tax_rate_boundary": 0.01,
    "strategy=tax_rate_interior": 0.99,
    # tax rates out of range: 50/50 split across negative / above-one
    "strategy=tax_rate_negative": 0.5,
    "strategy=tax_rate_above_one": 0.5,
    # optional descriptions: 1/3 each for None, padded, plain
    "strategy=description_none": 1 / 3,
    "strategy=description_padded": 1 / 3,
    "strategy=description_plain": 1 / 3,
    # reserve bytes in range: boundaries are rare (2 out of 256 values)
    "strategy=reserve_bytes_boundary": 0.01,
    "strategy=reserve_bytes_interior": 0.99,
    # reserve bytes out of range: 50/50 negative / overflow
    "strategy=reserve_bytes_negative": 0.5,
    "strategy=reserve_bytes_overflow": 0.5,
    # tax years in range: modern years dominate (100 out of 9999)
    "strategy=tax_year_boundary": 0.01,
    "strategy=tax_year_modern": 0.10,
    "strategy=tax_year_historic": 0.89,
    # tax years out of range: 50/50 zero-or-negative / overflow
    "strategy=tax_year_zero_or_negative": 0.5,
    "strategy=tax_year_overflow": 0.5,
}
