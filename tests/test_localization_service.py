"""Tests for FinestVX localization boot and fallback behavior."""

from __future__ import annotations

from pathlib import Path

import pytest
from ftllexengine.integrity import IntegrityCheckFailedError

from finestvx.legislation.lv import LatviaStandard2026Pack
from finestvx.localization import LocalizationConfig, LocalizationService


class TestLocalizationService:
    """Strict boot and fallback observability checks."""

    def test_latvia_pack_resources_boot_cleanly(self) -> None:
        """The bundled Latvia pack resources load without junk or missing files."""
        service = LatviaStandard2026Pack().create_localization()
        value, errors = service.format_value("latvia-pack-name")

        assert service.summary.all_clean is True
        assert errors == ()
        assert value == "Latvijas standarta pakotne 2026"

    def test_message_variable_schema_accepts_correct_variables(self, tmp_path: Path) -> None:
        """Boot succeeds when declared FTL variables match the expected schema exactly."""
        base_path = tmp_path / "locales"
        (base_path / "lv-LV").mkdir(parents=True)
        (base_path / "lv-LV" / "app.ftl").write_text(
            "greeting = Sveiks, { $name }!\n"
            "invoice-total = Kopsumma: { $amount } { $currency }\n",
            encoding="utf-8",
        )

        service = LocalizationService(
            LocalizationConfig(
                locales=("lv-LV",),
                resource_ids=("app.ftl",),
                base_path=base_path / "{locale}",
                message_variable_schemas={
                    "greeting": frozenset({"name"}),
                    "invoice-total": frozenset({"amount", "currency"}),
                },
            )
        )

        assert service.summary.all_clean is True

    def test_message_variable_schema_rejects_missing_variable(self, tmp_path: Path) -> None:
        """Boot fails when a required variable is absent from the FTL message."""
        base_path = tmp_path / "locales"
        (base_path / "lv-LV").mkdir(parents=True)
        (base_path / "lv-LV" / "app.ftl").write_text(
            "greeting = Sveiks, { $name }!\n",
            encoding="utf-8",
        )

        with pytest.raises(IntegrityCheckFailedError, match="variable mismatch"):
            LocalizationService(
                LocalizationConfig(
                    locales=("lv-LV",),
                    resource_ids=("app.ftl",),
                    base_path=base_path / "{locale}",
                    message_variable_schemas={"greeting": frozenset({"name", "title"})},
                )
            )

    def test_message_variable_schema_rejects_extra_variable(self, tmp_path: Path) -> None:
        """Boot fails when the FTL message declares a variable not in the expected schema."""
        base_path = tmp_path / "locales"
        (base_path / "lv-LV").mkdir(parents=True)
        (base_path / "lv-LV" / "app.ftl").write_text(
            "greeting = Sveiks, { $name } ({ $role })!\n",
            encoding="utf-8",
        )

        with pytest.raises(IntegrityCheckFailedError, match="variable mismatch"):
            LocalizationService(
                LocalizationConfig(
                    locales=("lv-LV",),
                    resource_ids=("app.ftl",),
                    base_path=base_path / "{locale}",
                    message_variable_schemas={"greeting": frozenset({"name"})},
                )
            )

    def test_fallback_events_are_recorded(self, tmp_path: Path) -> None:
        """Fallback resolution emits structured events from later locales."""
        base_path = tmp_path / "locales"
        (base_path / "lv-LV").mkdir(parents=True)
        (base_path / "en-US").mkdir(parents=True)
        (base_path / "lv-LV" / "app.ftl").write_text("only-lv = tikai latviski\n", encoding="utf-8")
        (base_path / "en-US" / "app.ftl").write_text(
            "fallback-message = fallback works\n",
            encoding="utf-8",
        )

        service = LocalizationService(
            LocalizationConfig(
                locales=("lv-LV", "en-US"),
                resource_ids=("app.ftl",),
                base_path=base_path / "{locale}",
            )
        )
        value, errors = service.format_value("fallback-message")

        assert value == "fallback works"
        assert errors == ()
        assert len(service.fallback_events) == 1
        assert service.fallback_events[0].resolved_locale == "en-US"
