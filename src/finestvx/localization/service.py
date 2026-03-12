"""Localization services built on top of FTLLexEngine's multi-locale runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ftllexengine import clear_module_caches
from ftllexengine import validate_message_variables as validate_ftl_message_variables
from ftllexengine.integrity import IntegrityCheckFailedError, IntegrityContext, SyntaxIntegrityError
from ftllexengine.localization.loading import PathResourceLoader
from ftllexengine.localization.orchestrator import FluentLocalization

from finestvx.persistence.config import MANDATED_CACHE_CONFIG

if TYPE_CHECKING:
    from collections.abc import Callable

    from ftllexengine import MessageVariableValidationResult
    from ftllexengine.localization.loading import FallbackInfo, LoadSummary
    from ftllexengine.localization.orchestrator import LocalizationCacheStats
    from ftllexengine.runtime.cache import WriteLogEntry
    from ftllexengine.runtime.cache_config import CacheConfig
    from ftllexengine.runtime.value_types import FluentValue
    from ftllexengine.syntax.ast import Message, Term

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
    message_variable_schemas: dict[str, frozenset[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize tuple storage and validate required fields."""
        object.__setattr__(self, "locales", tuple(self.locales))
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
        if config.message_variable_schemas:
            self._validate_message_schemas(config.message_variable_schemas)

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

    @staticmethod
    def _build_missing_message_error(message_id: str) -> IntegrityCheckFailedError:
        """Build the standard integrity error for absent message IDs."""
        context = IntegrityContext(
            component="localization",
            operation="boot-schema-validate",
            key=message_id,
            actual="not found",
        )
        msg = f"Schema validation: message {message_id!r} not found in any locale"
        return IntegrityCheckFailedError(msg, context=context)

    @staticmethod
    def _raise_for_schema_mismatch(result: MessageVariableValidationResult) -> None:
        """Raise the integrity error for a structured schema mismatch result."""
        parts: list[str] = []
        if result.missing_variables:
            parts.append(f"missing={sorted(result.missing_variables)!r}")
        if result.extra_variables:
            parts.append(f"extra={sorted(result.extra_variables)!r}")
        context = IntegrityContext(
            component="localization",
            operation="boot-schema-validate",
            key=result.message_id,
            actual=f"declared={sorted(result.declared_variables)!r}",
        )
        msg = f"FTL message {result.message_id!r} variable mismatch: {', '.join(parts)}"
        raise IntegrityCheckFailedError(msg, context=context)

    def _validate_message_schemas(self, schemas: dict[str, frozenset[str]]) -> None:
        """Validate each declared message's variables against the expected schema.

        Raises:
            IntegrityCheckFailedError: When a message is absent from all locales
                or its declared variables do not match the expected set exactly.
        """
        for message_id, expected_vars in schemas.items():
            result = self.validate_message_variables(message_id, expected_vars)
            if not result.is_valid:
                self._raise_for_schema_mismatch(result)

    @property
    def summary(self) -> LoadSummary:
        """Return the eager load summary produced at initialization."""
        return self._summary

    @property
    def fallback_events(self) -> tuple[FallbackInfo, ...]:
        """Return all recorded locale-fallback events."""
        return tuple(self._fallback_events)

    @property
    def cache_enabled(self) -> bool:
        """Return whether FTLLexEngine format caching is active."""
        return self._localization.cache_enabled

    @property
    def cache_config(self) -> CacheConfig | None:
        """Return the active FTLLexEngine cache configuration."""
        return self._localization.cache_config

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

    def get_message(self, message_id: str) -> Message | None:
        """Return the highest-priority message AST node from the fallback chain."""
        return self._localization.get_message(message_id)

    def get_term(self, term_id: str) -> Term | None:
        """Return the highest-priority term AST node from the fallback chain."""
        return self._localization.get_term(term_id)

    def validate_message_variables(
        self,
        message_id: str,
        expected_variables: frozenset[str] | set[str],
    ) -> MessageVariableValidationResult:
        """Validate a message's declared FTL variables against an expected schema."""
        message = self.get_message(message_id)
        if message is None:
            raise self._build_missing_message_error(message_id)
        return validate_ftl_message_variables(message, expected_variables)

    def clear_cache(self) -> None:
        """Clear all initialized FTLLexEngine bundle format caches."""
        self._localization.clear_cache()

    def get_cache_audit_log(self) -> dict[str, tuple[WriteLogEntry, ...]] | None:
        """Return immutable per-locale FTLLexEngine cache audit logs."""
        return self._localization.get_cache_audit_log()

    def get_cache_stats(self) -> LocalizationCacheStats | None:
        """Return aggregated cache statistics across all loaded bundles."""
        return self._localization.get_cache_stats()

    @staticmethod
    def clear_module_caches() -> None:
        """Clear all FTLLexEngine module-level caches."""
        clear_module_caches()
