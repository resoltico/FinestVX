"""Property tests for Latvia 2026 localization and rounding behavior."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest
from ftllexengine import make_fluent_number
from hypothesis import event, example, given
from hypothesis import strategies as st

from finestvx.legislation.lv.standard_2026 import round_eur


@pytest.mark.property
@pytest.mark.hypothesis
class TestLatviaStandard2026Properties:
    """Property checks for pack-local monetary formatting helpers."""

    @example(value=Decimal("10.005"))
    @given(
        value=st.one_of(
            st.integers(min_value=-1_000_000, max_value=1_000_000),
            st.decimals(
                min_value=Decimal("-999999.9999"),
                max_value=Decimal("999999.9999"),
                places=4,
                allow_nan=False,
                allow_infinity=False,
            ),
        )
    )
    def test_round_eur_matches_decimal_half_up_quantization(
        self,
        value: int | Decimal,
    ) -> None:
        """ROUND_EUR mirrors Decimal quantize with ROUND_HALF_UP."""
        decimal_value = Decimal(value) if isinstance(value, int) else value
        exponent = decimal_value.as_tuple().exponent
        visible_places = max(-exponent, 0) if isinstance(exponent, int) else 0

        event(f"strategy={'integer' if isinstance(value, int) else 'decimal'}")
        event(f"input_places={visible_places}")
        event(f"outcome=already_two_places_{visible_places == 2}")

        result = round_eur(make_fluent_number(value))

        assert result.decimal_value == decimal_value.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        assert result.precision == 2
