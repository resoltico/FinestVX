"""Localization services built on top of FTLLexEngine's multi-locale runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ftllexengine import clear_module_caches
from ftllexengine.integrity import IntegrityCheckFailedError, IntegrityContext, SyntaxIntegrityError
from ftllexengine.localization.loading import FallbackInfo, LoadSummary, PathResourceLoader
from ftllexengine.localization.orchestrator import FluentLocalization, LocalizationCacheStats
from ftllexengine.runtime.cache_config import CacheConfig
from ftllexengine.runtime.value_types import FluentValue

from finestvx.persistence.config import MANDATED_CACHE_CONFIG

__all__ = [
    "LocalizationConfig",
    "LocalizationService",
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

    def __post_init__(self) -> None:
        """Normalize tuple storage and validate required fields."""
        object.__setattr__(self, "locales", tuple(self.locales))
        object.__setattr__(self, "resource_ids", tuple(self.resource_ids))
        object.__setattr__(self, "base_path", Path(self.base_path))
        if len(self.locales) == 0:
            msg = "locales must not be empty"
            raise ValueError(msg)
        if len(self.resource_ids) == 0:
            msg = "resource_ids must not be empty"
            raise ValueError(msg)


class LocalizationService:
    """Thin wrapper around ``FluentLocalization`` with boot-time integrity checks."""

    __slots__ = ("_fallback_events", "_localization", "_summary")

    def __init__(
        self,
        config: LocalizationConfig,
        *,
        on_fallback: Callable[[FallbackInfo], None] | None = None,
    ) -> None:
        """Create the localization runtime and enforce clean boot semantics."""
        self._fallback_events: list[FallbackInfo] = []

        def record_fallback(info: FallbackInfo) -> None:
            self._fallback_events.append(info)
            if on_fallback is not None:
                on_fallback(info)

        loader = PathResourceLoader(str(config.base_path))
        self._localization = FluentLocalization(
            config.locales,
            config.resource_ids,
            loader,
            use_isolating=config.use_isolating,
            cache=config.cache,
            on_fallback=record_fallback,
            strict=config.strict,
        )
        self._summary = self._localization.get_load_summary()
        if config.require_all_clean and not self._summary.all_clean:
            self._raise_for_unclean_summary(self._summary)

    @staticmethod
    def _raise_for_unclean_summary(summary: LoadSummary) -> None:
        """Translate load-summary failures into integrity exceptions."""
        if summary.has_junk:
            first_junk_result = summary.get_with_junk()[0]
            context = IntegrityContext(
                component="localization",
                operation="boot-validate",
                key=first_junk_result.resource_id,
                actual=str(first_junk_result.source_path),
            )
            msg = "Localization resources contain Junk entries"
            raise SyntaxIntegrityError(
                msg,
                context=context,
                junk_entries=summary.get_all_junk(),
                source_path=first_junk_result.source_path,
            )
        error_results = summary.get_errors()
        if error_results:
            first_error = error_results[0]
            context = IntegrityContext(
                component="localization",
                operation="boot-load",
                key=first_error.resource_id,
                actual=str(first_error.error),
            )
            msg = (
                "Localization resource loading failed: "
                f"{first_error.locale}/{first_error.resource_id}"
            )
            raise IntegrityCheckFailedError(msg, context=context)
        not_found = summary.get_not_found()
        if not_found:
            first_missing = not_found[0]
            context = IntegrityContext(
                component="localization",
                operation="boot-load",
                key=first_missing.resource_id,
                actual="not found",
            )
            msg = (
                "Localization resource missing from fallback chain: "
                f"{first_missing.locale}/{first_missing.resource_id}"
            )
            raise IntegrityCheckFailedError(msg, context=context)

    @property
    def summary(self) -> LoadSummary:
        """Return the eager load summary produced at initialization."""
        return self._summary

    @property
    def fallback_events(self) -> tuple[FallbackInfo, ...]:
        """Return all recorded locale-fallback events."""
        return tuple(self._fallback_events)

    def format_value(
        self,
        message_id: str,
        args: dict[str, FluentValue] | None = None,
    ) -> tuple[str, tuple[object, ...]]:
        """Format a message value through the fallback chain."""
        return self._localization.format_value(message_id, args)

    def format_pattern(
        self,
        message_id: str,
        args: dict[str, FluentValue] | None = None,
        *,
        attribute: str | None = None,
    ) -> tuple[str, tuple[object, ...]]:
        """Format a message or attribute through the fallback chain."""
        return self._localization.format_pattern(message_id, args, attribute=attribute)

    def add_function(self, name: str, func: Callable[..., FluentValue]) -> None:
        """Register a custom function across all bundle instances."""
        self._localization.add_function(name, func)

    def get_cache_stats(self) -> LocalizationCacheStats | None:
        """Return aggregated cache statistics across all loaded bundles."""
        return self._localization.get_cache_stats()

    @staticmethod
    def clear_module_caches() -> None:
        """Clear all FTLLexEngine module-level caches."""
        clear_module_caches()
