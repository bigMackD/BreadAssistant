"""Ongoing processes reflect human events, including parallel work and recovery."""

from datetime import timedelta

import pytest

from custom_components.bread_assistant import scheduler
from custom_components.bread_assistant.i18n import Translator
from custom_components.bread_assistant.presentation import ongoing_processes
from custom_components.bread_assistant.serialization import bake_to_dict

from .test_schedule import START, bake


@pytest.mark.parametrize("language", ["en", "pl"])
def test_maturation_and_autolyse_overlap_without_changing_bake(language):
    b = bake()
    tr = Translator(language)
    assert ongoing_processes(b, tr) == []
    fed = START + timedelta(minutes=2)
    scheduler.complete(b, "feed_starter", fed)
    processes = ongoing_processes(b, tr)
    assert [p["id"] for p in processes] == ["starter"]
    assert processes[0]["started_at"] == fed.isoformat()
    assert processes[0]["title"] == (
        "Zakwas dojrzewa" if language == "pl" else "Starter is maturing"
    )
    scheduler.complete(b, "autolyse_start", START + timedelta(hours=3))
    scheduler.recompute(b, START + timedelta(hours=20))
    scheduler.lifecycle(b, "pause_bake", START + timedelta(hours=20))
    before = bake_to_dict(b)
    assert [p["id"] for p in ongoing_processes(b, tr)] == ["starter", "autolyse"]
    assert bake_to_dict(b) == before
    scheduler.lifecycle(b, "resume_bake", START + timedelta(hours=20))
    scheduler.complete(b, "autolyse_complete", START + timedelta(hours=20))
    assert [p["id"] for p in ongoing_processes(b, tr)] == ["starter"]
    scheduler.complete(b, "starter_ready", START + timedelta(hours=20))
    assert ongoing_processes(b, tr) == []


def test_prepared_starter_does_not_invent_feeding_or_maturation():
    b = bake(starter_workflow="prepared")
    assert ongoing_processes(b, Translator()) == []
    scheduler.complete(b, "autolyse_start", START)
    assert [p["id"] for p in ongoing_processes(b, Translator())] == ["autolyse"]
    scheduler.lifecycle(b, "cancel_bake", START)
    assert ongoing_processes(b, Translator()) == []


@pytest.mark.parametrize(
    ("step_id", "expected"),
    [
        ("knead_start", ["kneading"]),
        ("bulk_start", ["bulk"]),
        ("fold_1", ["bulk"]),
        ("fold_2", ["bulk"]),
        ("preshape", ["bench_rest"]),
        ("cold_proof_start", ["cold_proof"]),
        ("preheat_oven", ["cold_proof", "preheating"]),
        ("dough_ready", ["preheating"]),
        ("bake_start", ["covered_bake"]),
        ("remove_lid", ["uncovered_bake"]),
        ("bake_finish", ["cooling"]),
        ("cooling_start", ["cooling"]),
        ("cooling_check", []),
    ],
)
def test_processes_during_later_stages(step_id, expected):
    b = bake()
    while True:
        current = scheduler.actionable(b)[0]
        scheduler.complete(b, current.step_id, current.due_at)
        if current.step_id == step_id:
            break
    assert [p["id"] for p in ongoing_processes(b, Translator())] == expected


@pytest.mark.parametrize("language", ["en", "pl"])
async def test_sensor_processes_and_confirmation_labels_survive_reload(
    hass, integration, language
):
    c = integration.runtime_data
    c.options["language"] = language
    await c.async_action("start_bake", {})
    await c.async_action(
        "complete_step", {"bake_id": c.bake.id, "step_id": "feed_starter"}
    )
    state = hass.states.get("sensor.bread_assistant_current_step")
    assert state.attributes["step_id"] == "autolyse_start"
    expected = (
        "Potwierdź rozpoczęcie autolizy"
        if language == "pl"
        else "Confirm autolyse started"
    )
    assert state.attributes["confirmation_label"] == expected
    assert [p["id"] for p in state.attributes["ongoing_processes"]] == ["starter"]
    assert await hass.config_entries.async_reload(integration.entry_id)
    await hass.async_block_till_done()
    restored = hass.states.get("sensor.bread_assistant_current_step")
    assert [p["id"] for p in restored.attributes["ongoing_processes"]] == ["starter"]
