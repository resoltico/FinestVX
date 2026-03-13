"""Localization construction helpers built on top of FTLLexEngine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ftllexengine.core.locale_utils import require_locale_code
from ftllexengine.localization import FallbackInfo, FluentLocalization, PathResourceLoader

from finestvx.persistence.config import MANDATED_CACHE_CONFIG

if TYPE_CHECKING:
    from collections.abc import Callable

    from ftllexengine import CacheConfig

__all__ = [
    "LocalizationConfig",
    "create_localization",
]


@dataclass(frozen=True, slots=True)
class LocalizationConfig:
    """Configuration for FinestVX localization boot and fallback behavior."""

    locales: tuple[str, ...] | list[str]
    resource_ids: tuple[str, ...] | list[str]
    base_path: Path | str
    use_isolating: bool = True
    strict: bool = True
    require_all_clean: bool = True
    cache: CacheConfig = field(default=MANDATED_CACHE_CONFIG)
    message_variable_schemas: dict[str, frozenset[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize tuple storage and validate required fields."""
        normalized_locales = tuple(
            require_locale_code(locale, "locales")
            for locale in self.locales
        )
        object.__setattr__(self, "locales", normalized_locales)
        object.__setattr__(self, "resource_ids", tuple(self.resource_ids))
        object.__setattr__(self, "base_path", Path(self.base_path))
        object.__setattr__(
            self,
            "message_variable_schemas",
            {k: frozenset(v) for k, v in self.message_variable_schemas.items()},
        )
        if len(self.locales) == 0:
            msg = "locales must not be empty"
            raise ValueError(msg)
        if len(set(self.locales)) != len(self.locales):
            msg = "locales must be unique after normalization"
            raise ValueError(msg)
        if len(self.resource_ids) == 0:
            msg = "resource_ids must not be empty"
            raise ValueError(msg)


def create_localization(
    config: LocalizationConfig,
    *,
    on_fallback: Callable[[FallbackInfo], None] | None = None,
) -> FluentLocalization:
    """Create a strict FTLLexEngine localization runtime for FinestVX."""
    loader = PathResourceLoader(str(config.base_path))
    localization = FluentLocalization(
        config.locales,
        config.resource_ids,
        loader,
        use_isolating=config.use_isolating,
        cache=config.cache,
        on_fallback=on_fallback,
        strict=config.strict,
    )
    if config.require_all_clean:
        localization.require_clean()
    else:
        localization.get_load_summary()
    if config.message_variable_schemas:
        localization.validate_message_schemas(config.message_variable_schemas)
    return localization
