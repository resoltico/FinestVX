"""Registry for FinestVX legislative-pack implementations."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from finestvx.core.types import LegislativePackCode

from .lv.standard_2026 import LatviaStandard2026Pack
from .protocols import ILegislativePack

__all__ = [
    "LegislativePackRegistry",
    "create_default_pack_registry",
]


def _normalize_pack_code(pack_code: object) -> LegislativePackCode:
    """Validate and normalize a legislative-pack code."""
    if not isinstance(pack_code, str):
        msg = f"pack_code must be str, got {type(pack_code).__name__}"
        raise TypeError(msg)
    normalized = pack_code.strip()
    if not normalized:
        msg = "pack_code must not be empty"
        raise ValueError(msg)
    return normalized


class LegislativePackRegistry:
    """Mutable registry for resolving legislative-pack implementations."""

    __slots__ = ("_packs",)

    def __init__(self, packs: Iterable[ILegislativePack] = ()) -> None:
        """Initialize the registry and optionally pre-register packs."""
        self._packs: dict[LegislativePackCode, ILegislativePack] = {}
        for pack in packs:
            self.register(pack)

    def register(self, pack: ILegislativePack) -> None:
        """Register a legislative pack under its metadata code."""
        pack_code = _normalize_pack_code(pack.metadata.pack_code)
        if pack_code in self._packs:
            msg = f"Legislative pack already registered: {pack_code}"
            raise ValueError(msg)
        self._packs[pack_code] = pack

    def resolve(self, pack_code: LegislativePackCode) -> ILegislativePack:
        """Resolve a legislative pack or raise ``KeyError``."""
        normalized = _normalize_pack_code(pack_code)
        try:
            return self._packs[normalized]
        except KeyError as error:
            msg = f"Unknown legislative pack: {normalized}"
            raise KeyError(msg) from error

    def available_pack_codes(self) -> tuple[LegislativePackCode, ...]:
        """Return a stable list of registered pack codes."""
        return tuple(sorted(self._packs))

    def __contains__(self, pack_code: object) -> bool:
        """Return ``True`` when a pack code is registered."""
        return isinstance(pack_code, str) and pack_code in self._packs

    def __iter__(self) -> Iterator[LegislativePackCode]:
        """Iterate registered pack codes in insertion order."""
        return iter(self._packs)

    def __len__(self) -> int:
        """Return the number of registered packs."""
        return len(self._packs)


def create_default_pack_registry() -> LegislativePackRegistry:
    """Create the default registry containing the Latvia 2026 stub pack."""
    return LegislativePackRegistry((LatviaStandard2026Pack(),))
