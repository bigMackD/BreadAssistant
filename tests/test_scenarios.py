"""Whole-bake acceptance scenarios using simulated UTC clocks and real HA."""

from datetime import timedelta

import pytest

from custom_components.bread_assistant import scheduler
from custom_components.bread_assistant.models import BakeStatus, DomainError

from .test_schedule import START, bake


@pytest.mark.parametrize("workflow", ["feed", "prepared"])
async def test_complete_bake_in_ha_with_restart(hass, integration, workflow):
    c = integration.runtime_data
    await c.async_action("start_bake", {"starter_workflow": workflow})
    bake_id = c.bake.id
    restarted = False
    for _ in range(30):
        if c.bake.status == BakeStatus.COMPLETED:
            break
        current = c.current_steps()[0]
        now = max(c.clock(), current.due_at)
        c.clock = lambda now=now: now
        await c.async_action(
            "complete_step",
            {
                "bake_id": bake_id,
                "step_id": current.step_id,
            },
        )
        if current.step_id == "cold_proof_start" and not restarted:
            assert await hass.config_entries.async_unload(integration.entry_id)
            assert await hass.config_entries.async_setup(integration.entry_id)
            await hass.async_block_till_done()
            c = integration.runtime_data
            c.clock = lambda now=now: now
            restarted = True
    assert restarted
    assert c.bake.status == BakeStatus.COMPLETED
    assert c._cancel_timer is None
    assert len(c.archives) == 1
    assert hass.states.get("sensor.bread_assistant_progress").state == "100.0"
    revision = c.bake.revision
    await c.async_action(
        "complete_step", {"bake_id": bake_id, "step_id": "cooling_check"}
    )
    assert c.bake.revision == revision
    await c.async_action("start_bake", {})
    assert c.bake.id != bake_id


def test_oven_and_dough_gates_and_bake_segments():
    b = bake()
    for _ in range(20):
        current = scheduler.actionable(b)[0]
        if current.step_id == "dough_ready":
            break
        scheduler.complete(b, current.step_id, current.due_at)
    with pytest.raises(DomainError, match="prerequisites"):
        scheduler.complete(b, "bake_start", START + timedelta(days=2))
    scheduler.complete(b, "dough_ready", b.step_runs["dough_ready"].due_at)
    with pytest.raises(DomainError, match="prerequisites"):
        scheduler.complete(b, "bake_start", START + timedelta(days=2))
    scheduler.complete(b, "oven_ready", b.step_runs["oven_ready"].due_at)
    scheduler.complete(b, "score_loaf", b.step_runs["score_loaf"].due_at)
    scheduler.complete(b, "bake_start", b.step_runs["bake_start"].due_at)
    remove = b.step_runs["remove_lid"].due_at
    with pytest.raises(DomainError, match="deadline"):
        scheduler.complete(b, "remove_lid", remove - timedelta(minutes=1))
    scheduler.complete(b, "remove_lid", remove)
    with pytest.raises(DomainError, match="deadline"):
        scheduler.complete(b, "bake_finish", remove + timedelta(minutes=14))
    scheduler.complete(b, "bake_finish", remove + timedelta(minutes=15))
    assert b.step_runs["cooling_check"].due_at == remove + timedelta(minutes=135)
    assert b.status == BakeStatus.ACTIVE  # Cooling is still a manual checkpoint.
