"""Tests for FinestVX localization boot and fallback behavior."""

from __future__ import annotations

from pathlib import Path

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
