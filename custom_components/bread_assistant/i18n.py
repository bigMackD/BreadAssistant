"""Shared, HA-independent presentation lookup with per-key English fallback."""

import json
from functools import lru_cache
from pathlib import Path
from string import Formatter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import RecipeDefinition

ROOT = Path(__file__).parent


@lru_cache(maxsize=1)
def supported_languages() -> frozenset[str]:
    return frozenset(path.stem for path in (ROOT / "translations").glob("*.json"))


@lru_cache(maxsize=32)
def load_bundle(language: str) -> dict[str, Any]:
    """Read bundled assets only; HA preloads these in an executor."""
    result: dict[str, Any] = {}
    for directory, namespace in (("translations", None), ("localization", "content")):
        path = ROOT / directory / f"{language}.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if namespace:
                result[namespace] = data
            else:
                result.update(data)
    return result


def load_translations() -> None:
    """Preload all shipped languages before publishing entities or reminders."""
    for language in supported_languages():
        load_bundle(language)


def resolve_language(preference: str = "auto", system_language: str = "en") -> str:
    """Normalize regional variants; unsupported selections fall back to English."""
    language = system_language if preference == "auto" else preference
    language = (language or "en").lower().replace("_", "-").split("-", 1)[0]
    return language if language in supported_languages() else "en"


def _lookup(bundle: dict[str, Any], key: str) -> Any:
    value: Any = bundle
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _fields(value: str) -> set[str]:
    try:
        return {name for _, name, _, _ in Formatter().parse(value) if name is not None}
    except ValueError:
        return {"__invalid_format__"}


class Translator:
    """One lookup API for recipes, dashboard templates, pushes and diagnostics."""

    def __init__(self, language: str = "en") -> None:
        self.language = resolve_language(language)

    def text(self, key: str, *, fallback: str | None = None, **values: Any) -> str:
        english = _lookup(load_bundle("en"), key)
        translated = _lookup(load_bundle(self.language), key)
        if not isinstance(translated, str) or (
            isinstance(english, str) and _fields(translated) != _fields(english)
        ):
            translated = english
        if not isinstance(translated, str):
            translated = fallback if fallback is not None else key
        return translated.format(**values) if values else translated

    def section(self, key: str) -> dict[str, str]:
        """Return a flat string section, applying fallback independently per key."""
        english = _lookup(load_bundle("en"), key) or {}
        return {name: self.text(f"{key}.{name}") for name in english}

    def recipe(self, recipe: RecipeDefinition, field: str, fallback: str = "") -> str:
        """Versioned keys also localize legacy snapshots without rewriting them."""
        return self.text(
            f"content.recipes.{recipe.id}.v{recipe.version}.{field}",
            fallback=fallback,
        )

    def step(self, recipe: RecipeDefinition, step_id: str, field: str) -> str:
        definition = recipe.by_id[step_id]
        return self.recipe(
            recipe, f"steps.{step_id}.{field}", getattr(definition, field)
        )

    def error(self, error: Exception) -> str:
        """Translate domain errors recursively; preserve third-party diagnostics."""
        key = getattr(error, "translation_key", None)
        domain = getattr(error, "translation_domain", "bread_assistant")
        if not key or domain != "bread_assistant":
            return str(error)
        values = {
            key: self.error(value) if isinstance(value, Exception) else str(value)
            for key, value in (
                getattr(error, "placeholders", None)
                or getattr(error, "translation_placeholders", None)
                or {}
            ).items()
        }
        return self.text(f"exceptions.{key}.message", **values)
