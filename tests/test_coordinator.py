"""Restart-safe coordination, atomic changes, and timer lifecycle."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bread_assistant.const import DOMAIN
from custom_components.bread_assistant.coordinator import BakeCoordinator
from custom_components.bread_assistant.models import BakeStatus, DomainError, StepStatus
from custom_components.bread_assistant.storage import BakeStorage

from .test_schedule import START


@pytest.fixture
async def coordinator(hass, hass_storage):
    instance = BakeCoordinator(
        hass, MockConfigEntry(domain=DOMAIN, data={}), lambda: START
    )
    await instance.async_load()
    yield instance
    await instance.async_shutdown()


async def test_concurrent_completion_and_restart(coordinator, hass):
    await coordinator.async_action("start_bake", {})
    bake_id = coordinator.bake.id
    data = {"bake_id": bake_id, "step_id": "feed_starter"}
    await asyncio.gather(
        *(coordinator.async_action("complete_step", data) for _ in range(4))
    )
    assert coordinator.bake.revision == 1
    await coordinator.async_shutdown()
    restored = BakeCoordinator(
        hass, coordinator.entry, lambda: START + timedelta(hours=8)
    )
    await restored.async_load()
    assert restored.bake.id == bake_id
    assert restored.bake.step_runs["feed_starter"].completed_at == START
    with patch.object(restored, "_async_notify", new_callable=AsyncMock) as notify:
        await restored.async_tick(catchup=True)
        notify.assert_awaited_once()
        assert len(notify.call_args.args[0]) == 2  # starter + independent autolyse
        await restored.async_tick(catchup=True)
        notify.assert_awaited_once()
    await restored.async_shutdown()


async def test_failed_save_does_not_publish_or_change_state(coordinator):
    await coordinator.async_action("start_bake", {})
    original = coordinator.bake
    with patch.object(
        coordinator.storage, "async_save", side_effect=OSError("disk full")
    ):
        with pytest.raises(OSError):
            await coordinator.async_action("cancel_bake", {"bake_id": original.id})
    assert coordinator.bake is original
    assert coordinator.bake.status == BakeStatus.ACTIVE


async def test_pause_resume_cancel_and_shutdown(coordinator):
    await coordinator.async_action("start_bake", {})
    data = {"bake_id": coordinator.bake.id}
    due = coordinator.bake.step_runs["feed_starter"].due_at
    await coordinator.async_action("pause_bake", data)
    assert coordinator._cancel_timer is None
    coordinator.clock = lambda: START + timedelta(days=1)
    await coordinator.async_tick()
    assert coordinator.bake.status == BakeStatus.PAUSED
    await coordinator.async_action("resume_bake", data)
    assert coordinator.bake.step_runs["feed_starter"].due_at == due
    await coordinator.async_action("cancel_bake", data)
    assert len(coordinator.archives) == 1
    assert coordinator._cancel_timer is None
    with pytest.raises(DomainError):
        await coordinator.async_action(
            "complete_step", data | {"step_id": "feed_starter"}
        )
    await coordinator.async_action("start_bake", {})
    with pytest.raises(DomainError, match="stale"):
        await coordinator.async_action("cancel_bake", data)
    await coordinator.async_shutdown()
    assert coordinator._cancel_timer is None
    with pytest.raises(DomainError, match="unloading"):
        await coordinator.async_action("start_bake", {})


async def test_old_timer_callback_and_storage_retry(coordinator):
    callbacks = []

    def track(hass, callback, deadline):
        callbacks.append((callback, deadline))
        return lambda: None

    with patch(
        "custom_components.bread_assistant.coordinator.async_track_point_in_utc_time",
        track,
    ):
        await coordinator.async_action("start_bake", {})
        obsolete = callbacks[0][0]
        current = callbacks[-1][0]
        count = len(callbacks)
        await obsolete(START)
        assert len(callbacks) == count
        coordinator.clock = lambda: START + timedelta(hours=1)
        with patch.object(
            coordinator.storage, "async_save", side_effect=OSError("disk full")
        ):
            await current(coordinator.clock())
        assert "disk full" in coordinator.last_error
        assert callbacks[-1][1] == coordinator.clock() + timedelta(minutes=1)
        await coordinator.async_shutdown()
        count = len(callbacks)
        await callbacks[-1][0](coordinator.clock())
        assert len(callbacks) == count


async def test_shutdown_while_write_is_pending(coordinator):
    await coordinator.async_action("start_bake", {})
    entered = asyncio.Event()
    release = asyncio.Event()
    original_save = coordinator.storage.async_save

    async def slow_save(*args):
        entered.set()
        await release.wait()
        await original_save(*args)

    with patch.object(coordinator.storage, "async_save", side_effect=slow_save):
        mutation = asyncio.create_task(
            coordinator.async_action(
                "complete_step",
                {"bake_id": coordinator.bake.id, "step_id": "feed_starter"},
            )
        )
        await entered.wait()
        shutdown = asyncio.create_task(coordinator.async_shutdown())
        await asyncio.sleep(0)
        assert coordinator.closed
        release.set()
        await asyncio.gather(mutation, shutdown)
    assert coordinator._cancel_timer is None
    assert not coordinator._listeners


async def test_real_ha_deadline_with_simulated_time(coordinator, hass, freezer):
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    freezer.move_to(START)
    coordinator.clock = dt_util.utcnow
    with patch.object(coordinator, "_async_notify", new_callable=AsyncMock) as notify:
        await coordinator.async_action("start_bake", {})
        assert notify.await_count == 1
        future = START + timedelta(minutes=31)
        freezer.move_to(future)
        async_fire_time_changed(hass, future)
        await hass.async_block_till_done()
        assert notify.await_count == 2


async def test_startup_storage_failure_keeps_a_retry_scheduled(coordinator):
    await coordinator.async_action("start_bake", {})
    coordinator.clock = lambda: START + timedelta(hours=4)
    with patch.object(
        coordinator.storage, "async_save", side_effect=OSError("read-only")
    ):
        await coordinator._async_recover()
    assert "read-only" in coordinator.last_error
    assert coordinator._cancel_timer is not None
    await coordinator.async_tick()
    assert coordinator.last_error is None


@pytest.mark.parametrize("finish", ["complete", "cancel"])
async def test_archive_retains_step_times_across_new_bake_and_restart(
    coordinator, hass, finish
):
    await coordinator.async_action("start_bake", {"starter_workflow": "prepared"})
    bake_id = coordinator.bake.id
    while coordinator.bake.status == BakeStatus.ACTIVE:
        current = coordinator.current_steps()[0]
        coordinator.clock = lambda: START + timedelta(minutes=1)
        await coordinator.async_action(
            "complete_step", {"bake_id": bake_id, "step_id": current.step_id}
        )
        if finish == "cancel":
            await coordinator.async_action("cancel_bake", {"bake_id": bake_id})
    finished_bake = coordinator.bake
    await coordinator.async_action("start_bake", {})
    restored, archives = await BakeStorage(hass).async_load()
    assert restored.id != bake_id
    assert len(archives) == 1
    archive = archives[0]
    assert archive["id"] == bake_id
    assert archive["starter_workflow"] == "prepared"
    assert archive["step_runs"]["feed_starter"]["status"] == StepStatus.SKIPPED
    assert archive["step_runs"]["feed_starter"]["completed_at"] == START.isoformat()
    for step_id, run in finished_bake.step_runs.items():
        assert archive["step_runs"][step_id] == {
            "status": run.status,
            "planned_at": run.planned_at.isoformat(),
            "due_at": run.due_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
