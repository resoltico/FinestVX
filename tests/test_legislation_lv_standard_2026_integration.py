"""Integration tests for Latvia pack localization on top of FTLLexEngine."""

from __future__ import annotations

from decimal import Decimal

from ftllexengine import make_fluent_number
from ftllexengine.core.locale_utils import normalize_locale
from ftllexengine.localization import FluentLocalization

from finestvx.legislation.lv import LatviaStandard2026Pack
from finestvx.persistence import MANDATED_CACHE_CONFIG

_LV_LOCALE = normalize_locale("lv-LV")


class TestLatviaStandard2026LocalizationIntegration:
    """Pack-local localization must come from the upstream FTLLexEngine platform."""

    def test_pack_localization_boots_cleanly_with_mandated_cache_policy(self) -> None:
        """Pack localization uses strict upstream boot with FinestVX cache policy."""
        pack = LatviaStandard2026Pack()
        service, summary, _schema_results = pack.localization_boot_config().boot()
        pack.configure_localization(service)
        value, errors = service.format_value("latvia-pack-name")

        assert isinstance(service, FluentLocalization)
        assert summary.all_clean is True
        assert service.cache_enabled is True
        assert service.cache_config == MANDATED_CACHE_CONFIG
        assert errors == ()
        assert value == "Latvijas standarta pakotne 2026"

    def test_pack_localization_exposes_upstream_ast_schema_and_audit_surfaces(self) -> None:
        """Pack localization exposes FTLLexEngine runtime helpers directly."""
        pack = LatviaStandard2026Pack()
        service, _summary, _schema_results = pack.localization_boot_config().boot()
        pack.configure_localization(service)

        value, errors = service.format_value(
            "vat-amount",
            {"amount": make_fluent_number(Decimal("10.005"))},
        )
        message = service.get_message("vat-amount")
        schema_result = service.validate_message_variables("vat-standard-rate", frozenset({"rate"}))
        cache_stats = service.get_cache_stats()
        cache_audit_log = service.get_cache_audit_log()

        assert value.startswith("PVN summa: ")
        assert value.endswith(" EUR")
        assert "10.01" in value
        assert errors == ()
        assert message is not None
        assert schema_result.is_valid is True
        assert cache_stats is not None
        assert cache_stats["audit_enabled"] is True
        assert cache_audit_log is not None
        assert _LV_LOCALE in cache_audit_log
        assert len(cache_audit_log[_LV_LOCALE]) > 0
