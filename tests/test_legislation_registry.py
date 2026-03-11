"""Tests for FinestVX legislative-pack registry behavior."""

from __future__ import annotations

import pytest

from finestvx import LegislativePackRegistry, create_default_pack_registry
from finestvx.legislation.lv import LatviaStandard2026Pack


class TestLegislativePackRegistry:
    """Registry behavior and duplicate-handling tests."""

    def test_default_registry_contains_latvia_pack(self) -> None:
        """The default pack registry exposes the Latvia 2026 stub."""
        registry = create_default_pack_registry()

        assert "lv.standard.2026" in registry
        assert registry.available_pack_codes() == ("lv.standard.2026",)

    def test_duplicate_registration_is_rejected(self) -> None:
        """A pack code may only be registered once."""
        registry = LegislativePackRegistry((LatviaStandard2026Pack(),))

        with pytest.raises(ValueError, match="already registered"):
            registry.register(LatviaStandard2026Pack())

    def test_unknown_pack_resolution_raises_key_error(self) -> None:
        """Resolving an unknown pack produces a clear error."""
        registry = create_default_pack_registry()

        with pytest.raises(KeyError, match="Unknown legislative pack"):
            registry.resolve("missing.pack")
