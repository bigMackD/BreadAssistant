"""Load bundled, versioned definitions; reject ambiguous dependency graphs."""

import json
import re
from pathlib import Path
from typing import Any

from .models import (
    Dependency,
    DependencyKind,
    DomainError,
    RecipeDefinition,
    StepDefinition,
    StepKind,
    parse_time,
    utc,
)


def recipe_from_dict(data: dict[str, Any]) -> RecipeDefinition:
    """Deserialize and validate a recipe or a persisted immutable snapshot."""
    try:
        steps = tuple(
            StepDefinition(
                id=s["id"],
                title=s["title"],
                kind=StepKind(s["kind"]),
                instructions=s["instructions"],
                offset_minutes=s["offset_minutes"],
                dependencies=tuple(
                    Dependency(
                        kind=DependencyKind(d["kind"]),
                        offset_minutes=d.get("offset_minutes", 0),
                        anchor=d.get("anchor"),
                        at=parse_time(d["at"]) if d.get("at") else None,
                    )
                    for d in s["dependencies"]
                ),
                prerequisites=tuple(s.get("prerequisites", [])),
                duration_minutes=s.get("duration_minutes", 0),
                requires_confirmation=s.get("requires_confirmation", True),
                alert_policy=s.get("alert_policy", "due"),
                optional=s.get("optional", False),
                reference=s.get("reference", False),
                minimum_minutes=s.get("minimum_minutes"),
            )
            for s in data["steps"]
        )
        recipe = RecipeDefinition(
            id=data["id"],
            version=data["version"],
            title=data["title"],
            url=data["url"],
            ingredients=tuple(data["ingredients"]),
            steps=steps,
        )
        validate_recipe(recipe)
        return recipe
    except (KeyError, TypeError, ValueError) as err:
        raise DomainError("invalid_recipe", error=err) from err


def topological_steps(recipe: RecipeDefinition) -> list[StepDefinition]:
    by_id = recipe.by_id
    visiting: set[str] = set()
    visited: set[str] = set()
    result: list[StepDefinition] = []

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise DomainError("cycle")
        if step_id in visited:
            return
        if step_id not in by_id:
            raise DomainError("step_unknown", step_id=step_id)
        visiting.add(step_id)
        step = by_id[step_id]
        for anchor in (*step.prerequisites, *(d.anchor for d in step.dependencies)):
            if anchor is not None:
                visit(anchor)
        visiting.remove(step_id)
        visited.add(step_id)
        result.append(step)

    for step in recipe.steps:
        visit(step.id)
    return result


def validate_recipe(recipe: RecipeDefinition) -> None:
    if not recipe.steps or len(recipe.steps) > 64:
        raise DomainError("step_count")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", recipe.id):
        raise DomainError("recipe_id")
    if type(recipe.version) is not int or recipe.version < 1:
        raise DomainError("recipe_version")
    if len(recipe.by_id) != len(recipe.steps):
        raise DomainError("duplicate_step")
    for step in recipe.steps:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", step.id):
            raise DomainError("step_id")
        if not step.title or len(step.title) > 120 or not step.instructions:
            raise DomainError("missing_text")
        if len(step.instructions) > 1000:
            raise DomainError("long_instructions")
        if step.alert_policy not in ("due", "silent"):
            raise DomainError("alert_policy")
        if not step.dependencies:
            raise DomainError("dependency_missing")
        for minutes in (step.offset_minutes, step.duration_minutes):
            if type(minutes) is not int or not 0 <= minutes <= 525600:
                raise DomainError("duration")
        if len(step.prerequisites) != len(set(step.prerequisites)):
            raise DomainError("duplicate_prerequisite")
        if step.minimum_minutes is not None and (
            type(step.minimum_minutes) is not int
            or not 0 <= step.minimum_minutes <= step.duration_minutes
        ):
            raise DomainError("minimum_duration")
        seen: set[tuple[DependencyKind, str | None]] = set()
        for dep in step.dependencies:
            if (
                type(dep.offset_minutes) is not int
                or not 0 <= dep.offset_minutes <= 525600
            ):
                raise DomainError("dependency_offset")
            if (dep.kind, dep.anchor) in seen:
                raise DomainError("duplicate_anchor")
            seen.add((dep.kind, dep.anchor))
            anchored = dep.kind in (
                DependencyKind.AFTER_COMPLETION,
                DependencyKind.PARALLEL_ANCHOR,
            )
            if anchored != (dep.anchor is not None):
                raise DomainError("anchor")
            if (dep.kind == DependencyKind.ABSOLUTE) != (dep.at is not None):
                raise DomainError("absolute_time")
            if dep.at is not None:
                utc(dep.at)
    topological_steps(recipe)


def load_catalog() -> dict[str, RecipeDefinition]:
    """Disk IO: call from an executor in HA."""
    recipes = [
        recipe_from_dict(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((Path(__file__).parent / "recipes").glob("*.json"))
    ]
    if not recipes or len({r.id for r in recipes}) != len(recipes):
        raise DomainError("catalog")
    return {r.id: r for r in recipes}
