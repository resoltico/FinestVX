"""Property-based tests for FinestVX localization schema validation."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from ftllexengine import validate_message_variables
from ftllexengine.core.locale_utils import normalize_locale
from hypothesis import event, given
from hypothesis import strategies as st

from finestvx.localization import LocalizationConfig, create_localization

_VARIABLE_NAMES = ("amount", "currency", "name", "ref", "role", "title", "total")
_LV_LOCALE = normalize_locale("lv-LV")


def _render_message_source(variables: frozenset[str]) -> str:
    """Render a minimal FTL resource for a declared variable set."""
    if len(variables) == 0:
        return "message = Static text\n"
    placeables = " ".join(f"{{ ${name} }}" for name in sorted(variables))
    return f"message = {placeables}\n"


@pytest.mark.property
@pytest.mark.hypothesis
class TestLocalizationServiceProperties:
    """Property checks for structured FTL schema validation."""

    @given(
        declared=st.frozensets(st.sampled_from(_VARIABLE_NAMES), max_size=4),
        expected=st.frozensets(st.sampled_from(_VARIABLE_NAMES), max_size=4),
    )
    def test_validate_message_variables_reports_exact_set_diffs(
        self,
        declared: frozenset[str],
        expected: frozenset[str],
    ) -> None:
        """Structured validation results match the mathematical set differences."""
        event(f"declared_count={len(declared)}")
        event(f"expected_count={len(expected)}")
        event(f"outcome=valid_{declared == expected}")

        with TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / "locales"
            (base_path / _LV_LOCALE).mkdir(parents=True)
            (base_path / _LV_LOCALE / "app.ftl").write_text(
                _render_message_source(declared),
                encoding="utf-8",
            )

            service = create_localization(
                LocalizationConfig(
                    locales=("lv-LV",),
                    resource_ids=("app.ftl",),
                    base_path=base_path / "{locale}",
                )
            )

            message = service.get_message("message")

            assert message is not None
            result = validate_message_variables(message, expected)

            assert result.message_id == "message"
            assert result.declared_variables == declared
            assert result.missing_variables == expected - declared
            assert result.extra_variables == declared - expected
            assert result.is_valid is (declared == expected)
