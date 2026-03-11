"""Additional tests for FinestVX localization services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from ftllexengine.integrity import IntegrityCheckFailedError, SyntaxIntegrityError

import finestvx.localization.service as localization_module
from finestvx.legislation.lv import LatviaStandard2026Pack
from finestvx.localization import LocalizationConfig, LocalizationService


@dataclass(frozen=True)
class _FakeJunkResult:
    """Minimal junk result for localization-summary failure tests."""

    resource_id: str
    source_path: Path


@dataclass(frozen=True)
class _FakeErrorResult:
    """Minimal error result for localization-summary failure tests."""

    resource_id: str
    locale: str
    error: Exception


@dataclass(frozen=True)
class _FakeMissingResult:
    """Minimal not-found result for localization-summary failure tests."""

    resource_id: str
    locale: str


@dataclass(frozen=True)
class _FakeSummary:
    """Minimal load summary matching the wrapper's needs."""

    has_junk: bool = False
    junk_results: tuple[_FakeJunkResult, ...] = ()
    error_results: tuple[_FakeErrorResult, ...] = ()
    missing_results: tuple[_FakeMissingResult, ...] = ()

    def get_with_junk(self) -> tuple[_FakeJunkResult, ...]:
        """Return junk-bearing results."""
        return self.junk_results

    def get_all_junk(self) -> tuple[str, ...]:
        """Return placeholder junk entries."""
        return ("junk-entry",)

    def get_errors(self) -> tuple[_FakeErrorResult, ...]:
        """Return load errors."""
        return self.error_results

    def get_not_found(self) -> tuple[_FakeMissingResult, ...]:
        """Return missing resources."""
        return self.missing_results


class TestLocalizationServiceEdges:
    """Boot validation, fallback auditing, and pass-through helpers."""

    def test_config_normalizes_paths_and_rejects_empty_inputs(self, tmp_path: Path) -> None:
        """Localization config stores tuple/path values and rejects empty collections."""
        config = LocalizationConfig(
            locales=["lv-LV", "en-US"],
            resource_ids=["app.ftl"],
            base_path=tmp_path / "{locale}",
        )

        assert config.locales == ("lv-LV", "en-US")
        assert config.resource_ids == ("app.ftl",)
        assert config.base_path == tmp_path / "{locale}"

        with pytest.raises(ValueError, match="locales must not be empty"):
            LocalizationConfig(
                locales=(),
                resource_ids=("app.ftl",),
                base_path=tmp_path / "{locale}",
            )
        with pytest.raises(ValueError, match="resource_ids must not be empty"):
            LocalizationConfig(
                locales=("lv-LV",),
                resource_ids=(),
                base_path=tmp_path / "{locale}",
            )

    def test_unclean_boot_raises_for_junk_error_and_missing_resources(self, tmp_path: Path) -> None:
        """Boot-time validation translates load-summary failures into integrity exceptions."""
        junk_path = tmp_path / "junk"
        (junk_path / "lv-LV").mkdir(parents=True)
        (junk_path / "lv-LV" / "app.ftl").write_text("broken = {\n", encoding="utf-8")
        with pytest.raises(SyntaxIntegrityError, match="syntax error"):
            LocalizationService(
                LocalizationConfig(
                    locales=("lv-LV",),
                    resource_ids=("app.ftl",),
                    base_path=junk_path / "{locale}",
                )
            )
        with pytest.raises(
            SyntaxIntegrityError,
            match="Localization resources contain Junk entries",
        ):
            LocalizationService._raise_for_unclean_summary(
                cast(
                    Any,
                    _FakeSummary(
                        has_junk=True,
                        junk_results=(
                            _FakeJunkResult(
                                resource_id="app.ftl",
                                source_path=junk_path / "lv-LV" / "app.ftl",
                            ),
                        ),
                    ),
                ),
            )

        with pytest.raises(
            IntegrityCheckFailedError,
            match="Localization resource loading failed",
        ):
            LocalizationService._raise_for_unclean_summary(
                cast(
                    Any,
                    _FakeSummary(
                        error_results=(
                            _FakeErrorResult(
                                resource_id="app.ftl",
                                locale="lv-LV",
                                error=OSError("disk error"),
                            ),
                        ),
                    ),
                ),
            )
        with pytest.raises(IntegrityCheckFailedError, match="Localization resource missing"):
            LocalizationService._raise_for_unclean_summary(
                cast(
                    Any,
                    _FakeSummary(
                        missing_results=(
                            _FakeMissingResult(resource_id="app.ftl", locale="lv-LV"),
                        ),
                    ),
                )
            )

    def test_service_records_fallbacks_and_exposes_pass_through_helpers(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """The wrapper exposes formatting, cache stats, and function registration."""
        base_path = tmp_path / "locales"
        (base_path / "lv-LV").mkdir(parents=True)
        (base_path / "en-US").mkdir(parents=True)
        (base_path / "lv-LV" / "app.ftl").write_text(
            "message = Primary\n    .hint = Primary hint\n",
            encoding="utf-8",
        )
        (base_path / "en-US" / "app.ftl").write_text(
            "fallback-message = Fallback\n",
            encoding="utf-8",
        )

        callback_events: list[object] = []
        service = LocalizationService(
            LocalizationConfig(
                locales=("lv-LV", "en-US"),
                resource_ids=("app.ftl",),
                base_path=base_path / "{locale}",
            ),
            on_fallback=callback_events.append,
        )

        hint_value, hint_errors = service.format_pattern("message", attribute="hint")
        fallback_value, fallback_errors = service.format_value("fallback-message")

        clear_calls: list[str] = []
        monkeypatch.setattr(
            localization_module,
            "clear_module_caches",
            lambda: clear_calls.append("ok"),
        )

        service.add_function("ECHO", lambda: "x")
        cache_stats = service.get_cache_stats()
        service.clear_module_caches()

        assert service.summary.all_clean is True
        assert hint_value == "Primary hint"
        assert hint_errors == ()
        assert fallback_value == "Fallback"
        assert fallback_errors == ()
        assert len(service.fallback_events) == 1
        assert len(callback_events) == 1
        assert cache_stats is not None
        assert clear_calls == ["ok"]

    def test_pack_localization_exposes_cache_stats(self) -> None:
        """Pack-provided localization services are usable directly."""
        service = LatviaStandard2026Pack().create_localization()

        value, errors = service.format_pattern("latvia-pack-name")

        assert value == "Latvijas standarta pakotne 2026"
        assert errors == ()
        assert service.get_cache_stats() is not None
