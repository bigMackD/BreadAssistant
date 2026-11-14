"""Catalog validation rejects unsafe or ambiguous schedules."""

from dataclasses import replace
from datetime import datetime

import pytest

from custom_components.bread_assistant.models import (
    Dependency,
    DependencyKind,
    DomainError,
)
from custom_components.bread_assistant.recipe_catalog import (
    load_catalog,
    validate_recipe,
)


def test_recipe_milestones():
    recipe = next(iter(load_catalog().values()))
    assert [s.offset_minutes for s in recipe.steps if s.reference] == [
        0,
        180,
        240,
        245,
        275,
        305,
        545,
        555,
        560,
        1240,
        1280,
        1320,
    ]
    assert len(recipe.ingredients) == 3


@pytest.mark.parametrize(
    "error", ["duplicate", "unknown", "cycle", "negative", "anchor"]
)
def test_invalid_recipe(error):
    recipe = next(iter(load_catalog().values()))
    first = recipe.steps[0]
    if error == "duplicate":
        recipe = replace(recipe, steps=(*recipe.steps, first))
    else:
        first = replace(
            first,
            **{
                "unknown": {"prerequisites": ("missing",)},
                "cycle": {"prerequisites": ("knead_start",)},
                "negative": {"duration_minutes": -1},
                "anchor": {
                    "dependencies": (
                        Dependency(DependencyKind.AFTER_START, anchor="fold_1"),
                    )
                },
            }[error],
        )
        recipe = replace(recipe, steps=(first, *recipe.steps[1:]))
    with pytest.raises(DomainError):
        validate_recipe(recipe)


def test_absolute_dependency_rejects_naive_timestamp():
    recipe = next(iter(load_catalog().values()))
    first = replace(
        recipe.steps[0],
        dependencies=(Dependency(DependencyKind.ABSOLUTE, at=datetime(2026, 11, 14)),),
    )
    with pytest.raises(DomainError, match="timezone"):
        validate_recipe(replace(recipe, steps=(first, *recipe.steps[1:])))
