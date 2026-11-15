"""Exact supplied Polish passages, all checkpoints and unchanged bake snapshots."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from custom_components.bread_assistant.i18n import Translator
from custom_components.bread_assistant.models import BakeStatus
from custom_components.bread_assistant.recipe_catalog import load_catalog
from custom_components.bread_assistant.serialization import bake_to_dict

SECTIONS = json.loads(
    Path("tests/fixtures/justyna_method_pl.json").read_text(encoding="utf-8")
)
PASSAGES = {
    "feed_starter": ("feeding",),
    "autolyse_start": ("autolyse",),
    "starter_ready": ("feeding",),
    "autolyse_complete": ("autolyse",),
    "knead_start": ("kneading",),
    "bulk_start": ("bulk",),
    "fold_1": ("folding",),
    "fold_2": ("folding",),
    "bulk_ready": ("bulk", "folding"),
    "preshape": ("preshape",),
    "final_shape": ("final_shape",),
    "cold_proof_start": ("cold_proof",),
    "preheat_oven": ("preheat",),
    "dough_ready": ("dough_ready",),
    "oven_ready": ("preheat",),
    "score_loaf": ("scoring",),
    "bake_start": ("baking",),
    "remove_lid": ("baking",),
    "bake_finish": ("baking", "cooling"),
    "cooling_start": ("cooling",),
    "cooling_check": ("cooling",),
}


def test_all_polish_passages_preserve_supplied_wording():
    recipe = next(iter(load_catalog().values()))
    tr = Translator("pl")
    assert set(PASSAGES) == {step.id for step in recipe.steps}
    assert {section for sections in PASSAGES.values() for section in sections} == set(
        SECTIONS
    )
    for step_id, sections in PASSAGES.items():
        assert tr.step(recipe, step_id, "instructions") == "\n\n".join(
            SECTIONS[section] for section in sections
        )


@pytest.mark.parametrize("language", ["en", "pl"])
def test_legacy_short_snapshots_receive_full_instructions(language):
    recipe = next(iter(load_catalog().values()))
    legacy = replace(
        recipe,
        steps=tuple(
            replace(step, instructions="Previous short instruction")
            for step in recipe.steps
        ),
    )
    tr = Translator(language)
    for step in legacy.steps:
        assert tr.step(legacy, step.id, "instructions") == tr.step(
            recipe, step.id, "instructions"
        )
        assert step.instructions == "Previous short instruction"
    assert tr.recipe(legacy, "instructions_attribution")


@pytest.mark.parametrize("language", ["en", "pl"])
async def test_every_current_step_exposes_full_text_separate_summary_and_hint(
    hass, integration, language
):
    c = integration.runtime_data
    c.options["language"] = language
    await c.async_action("start_bake", {})
    seen = set()
    tr = Translator(language)
    while c.bake.status != BakeStatus.COMPLETED:
        current = c.current_steps()[0]
        now = max(c.clock(), current.due_at)
        c.clock = lambda now=now: now
        await hass.async_block_till_done()
        before = bake_to_dict(c.bake)
        state = hass.states.get("sensor.bread_assistant_current_step")
        attrs = state.attributes
        assert attrs["step_id"] == current.step_id
        assert attrs["instructions"] == tr.step(
            c.bake.recipe_snapshot, current.step_id, "instructions"
        )
        assert attrs["instructions_summary"]
        assert attrs["instructions_summary"] != attrs["instructions"]
        assert attrs["confirmation_hint"]
        assert "Justyna Dragan" in attrs["instructions_attribution"]
        assert bake_to_dict(c.bake) == before
        seen.add(current.step_id)
        await c.async_action(
            "complete_step", {"bake_id": c.bake.id, "step_id": current.step_id}
        )
    assert seen == set(PASSAGES)


@pytest.mark.parametrize("language", ["en", "pl"])
def test_cooling_guidance_distinguishes_recipe_from_reminder(language):
    recipe = next(iter(load_catalog().values()))
    tr = Translator(language)
    assert "20 minut" in tr.step(recipe, "cooling_check", "instructions") or (
        "20 minutes" in tr.step(recipe, "cooling_check", "instructions")
    )
    hint = tr.recipe(recipe, "steps.cooling_check.confirmation_hint")
    assert "2 godzin" in hint or "2 hours" in hint
