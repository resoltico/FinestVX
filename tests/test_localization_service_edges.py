"""Additional tests for FinestVX localization services."""

from __future__ import annotations

from pathlib import Path

import pytest
from ftllexengine import clear_module_caches
from ftllexengine.core.locale_utils import normalize_locale
from ftllexengine.integrity import IntegrityCheckFailedError, SyntaxIntegrityError
from ftllexengine.localization import FallbackInfo

from finestvx.legislation.lv import LatviaStandard2026Pack
from finestvx.localization import LocalizationConfig, create_localization

_LV_LOCALE = normalize_locale("lv-LV")
_EN_LOCALE = normalize_locale("en-US")


class TestLocalizationServiceEdges:
    """Boot validation, locale normalization, and direct FTLLexEngine helpers."""

    def test_config_normalizes_locales_and_rejects_invalid_inputs(self, tmp_path: Path) -> None:
        """LocalizationConfig stores canonical locale codes and rejects invalid input."""
        config = LocalizationConfig(
            locales=["lv-LV", "en-US"],
            resource_ids=["app.ftl"],
            base_path=tmp_path / "{locale}",
        )

        assert config.locales == (_LV_LOCALE, _EN_LOCALE)
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
        with pytest.raises(ValueError, match="Invalid locales"):
            LocalizationConfig(
                locales=("lv/LV",),
                resource_ids=("app.ftl",),
                base_path=tmp_path / "{locale}",
            )
        with pytest.raises(ValueError, match="unique after normalization"):
            LocalizationConfig(
                locales=("lv-LV", "lv_lv"),
                resource_ids=("app.ftl",),
                base_path=tmp_path / "{locale}",
            )

    def test_strict_boot_raises_on_broken_and_missing_resources(self, tmp_path: Path) -> None:
        """Strict boot propagates upstream require_clean failures directly."""
        broken_path = tmp_path / "broken"
        (broken_path / _LV_LOCALE).mkdir(parents=True)
        (broken_path / _LV_LOCALE / "app.ftl").write_text("broken = {\n", encoding="utf-8")

        with pytest.raises(SyntaxIntegrityError, match="Strict mode"):
            create_localization(
                LocalizationConfig(
                    locales=("lv-LV",),
                    resource_ids=("app.ftl",),
                    base_path=broken_path / "{locale}",
                )
            )

        with pytest.raises(IntegrityCheckFailedError, match="Localization initialization is not clean"):
            create_localization(
                LocalizationConfig(
                    locales=("lv-LV",),
                    resource_ids=("missing.ftl",),
                    base_path=broken_path / "{locale}",
                )
            )

    def test_service_records_fallbacks_and_exposes_pass_through_helpers(
        self,
        tmp_path: Path,
    ) -> None:
        """The constructor returns a usable FTLLexEngine localization runtime."""
        base_path = tmp_path / "locales"
        (base_path / _LV_LOCALE).mkdir(parents=True)
        (base_path / _EN_LOCALE).mkdir(parents=True)
        (base_path / _LV_LOCALE / "app.ftl").write_text(
            "-brand = FinestVX\n"
            "message = Primary\n"
            "    .hint = Primary hint\n"
            "schema-message = Sveiks, { $name }!\n",
            encoding="utf-8",
        )
        (base_path / _EN_LOCALE / "app.ftl").write_text(
            "fallback-message = Fallback\n",
            encoding="utf-8",
        )

        callback_events: list[FallbackInfo] = []
        service = create_localization(
            LocalizationConfig(
                locales=("lv-LV", "en-US"),
                resource_ids=("app.ftl",),
                base_path=base_path / "{locale}",
            ),
            on_fallback=callback_events.append,
        )

        hint_value, hint_errors = service.format_pattern("message", attribute="hint")
        fallback_value, fallback_errors = service.format_value("fallback-message")

        service.add_function("ECHO", lambda: "x")
        message = service.get_message("schema-message")
        term = service.get_term("brand")
        schema_result = service.validate_message_variables(
            "schema-message",
            frozenset({"name"}),
        )
        schema_results = service.validate_message_schemas(
            {"schema-message": frozenset({"name"})}
        )
        cache_stats = service.get_cache_stats()
        cache_audit_log = service.get_cache_audit_log()
        service.clear_cache()
        clear_module_caches()

        assert service.get_load_summary().all_clean is True
        assert service.cache_enabled is True
        assert service.cache_config is not None
        assert service.cache_config.enable_audit is True
        assert hint_value == "Primary hint"
        assert hint_errors == ()
        assert fallback_value == "Fallback"
        assert fallback_errors == ()
        assert message is not None
        assert term is not None
        assert schema_result.is_valid is True
        assert schema_result.declared_variables == frozenset({"name"})
        assert len(schema_results) == 1
        assert schema_results[0] == schema_result
        assert len(callback_events) == 1
        assert callback_events[0].resolved_locale == _EN_LOCALE
        assert cache_stats is not None
        assert cache_stats["audit_enabled"] is True
        assert cache_audit_log is not None
        assert set(cache_audit_log) == {_EN_LOCALE, _LV_LOCALE}
        assert len(cache_audit_log[_LV_LOCALE]) > 0
        assert len(cache_audit_log[_EN_LOCALE]) > 0

    def test_pack_localization_exposes_cache_stats(self) -> None:
        """Pack-provided localization services are usable directly."""
        service = LatviaStandard2026Pack().create_localization()

        value, errors = service.format_pattern("latvia-pack-name")
        cache_audit_log = service.get_cache_audit_log()

        assert value == "Latvijas standarta pakotne 2026"
        assert errors == ()
        assert service.get_cache_stats() is not None
        assert cache_audit_log is not None
        assert _LV_LOCALE in cache_audit_log

    def test_config_message_variable_schemas_normalizes_set_to_frozenset(
        self, tmp_path: Path
    ) -> None:
        """LocalizationConfig stores schema sets as frozenset values."""
        config = LocalizationConfig(
            locales=("lv-LV",),
            resource_ids=("app.ftl",),
            base_path=tmp_path / "{locale}",
            message_variable_schemas={"greeting": frozenset({"name", "title"})},
        )

        assert isinstance(config.message_variable_schemas["greeting"], frozenset)
        assert config.message_variable_schemas["greeting"] == frozenset({"name", "title"})

    def test_config_message_variable_schemas_defaults_to_empty_dict(
        self, tmp_path: Path
    ) -> None:
        """LocalizationConfig defaults message_variable_schemas to an empty dict."""
        config = LocalizationConfig(
            locales=("lv-LV",),
            resource_ids=("app.ftl",),
            base_path=tmp_path / "{locale}",
        )

        assert config.message_variable_schemas == {}

    def test_schema_validation_rejects_unknown_message_id(self, tmp_path: Path) -> None:
        """Boot fails when schema validation names a missing message."""
        base_path = tmp_path / "locales"
        (base_path / _LV_LOCALE).mkdir(parents=True)
        (base_path / _LV_LOCALE / "app.ftl").write_text(
            "greeting = Sveiks!\n",
            encoding="utf-8",
        )

        with pytest.raises(
            IntegrityCheckFailedError,
            match="Localization message schema validation failed",
        ):
            create_localization(
                LocalizationConfig(
                    locales=("lv-LV",),
                    resource_ids=("app.ftl",),
                    base_path=base_path / "{locale}",
                    message_variable_schemas={"nonexistent-message": frozenset({"name"})},
                )
            )

    def test_schema_validation_error_message_names_both_missing_and_extra(
        self, tmp_path: Path
    ) -> None:
        """Schema mismatch errors include both missing and extra variable groups."""
        base_path = tmp_path / "locales"
        (base_path / _LV_LOCALE).mkdir(parents=True)
        (base_path / _LV_LOCALE / "app.ftl").write_text(
            "invoice = Nr. { $ref } summa { $amount }\n",
            encoding="utf-8",
        )

        with pytest.raises(IntegrityCheckFailedError) as exc_info:
            create_localization(
                LocalizationConfig(
                    locales=("lv-LV",),
                    resource_ids=("app.ftl",),
                    base_path=base_path / "{locale}",
                    message_variable_schemas={"invoice": frozenset({"id", "total"})},
                )
            )

        error_text = str(exc_info.value)
        assert "missing {" in error_text
        assert "extra {" in error_text
