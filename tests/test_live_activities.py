"""Live Activity lifecycle with real HA Store/timers and mocked phone services."""

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import Event
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bread_assistant.const import DOMAIN
from custom_components.bread_assistant.coordinator import BakeCoordinator
from custom_components.bread_assistant.live_activities import (
    RENEW_AFTER,
    RETRY_AFTER,
    activity_tag,
)
from custom_components.bread_assistant.models import BakeStatus

from .test_schedule import START

TARGET = "notify.mobile_app_live_phone"


@pytest.fixture
async def live(hass, hass_storage):
    deliveries = []

    async def notify(call):
        deliveries.append(dict(call.data))

    hass.services.async_register("notify", "mobile_app_live_phone", notify)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "notifications_enabled": False,
            "live_activities_enabled": True,
            "live_activity_notify_target": TARGET,
        },
    )
    c = BakeCoordinator(hass, entry, lambda: START)
    await c.async_load()
    yield c, deliveries
    await c.async_shutdown()


def updates(deliveries):
    return [d for d in deliveries if d["message"] != "clear_notification"]


async def complete(c, step_id, at=None):
    if at is not None:
        c.clock = lambda: at
    await c.async_action("complete_step", {"bake_id": c.bake.id, "step_id": step_id})


async def restart(c, hass, at, options=None):
    await c.async_shutdown()
    entry = c.entry if options is None else MockConfigEntry(domain=DOMAIN, data=options)
    restored = BakeCoordinator(hass, entry, lambda: at)
    await restored.async_load()
    await restored._async_recover()
    return restored


async def test_creation_step_completion_countdown_and_dedup(live):
    c, deliveries = live
    await c.async_action("start_bake", {})
    assert len(deliveries) == 1
    first = deliveries[0]
    tag = first["data"]["tag"]
    assert tag == activity_tag(c.bake.id)
    assert len(tag) <= 64
    assert first["title"] == "Bread Assistant"
    assert "Feed starter" in first["message"]
    assert first["data"]["live_update"] is True
    assert first["data"]["progress"] == 0
    assert first["data"]["chronometer"] is False  # Already due.
    assert "actions" not in first["data"]
    await complete(c, "feed_starter")
    assert len(deliveries) == 2
    data = deliveries[-1]["data"]
    assert data["tag"] == tag
    assert data["progress"] == 1
    assert data["chronometer"] is True
    assert data["when"] == int(c.current_steps()[0].due_at.timestamp())
    assert data["when_relative"] is False
    assert data["silent"] is True
    assert data["url"] == c.options["dashboard_path"]
    for minute in (1, 10, 30):
        c.clock = lambda minute=minute: START + timedelta(minutes=minute)
        await c.async_tick()
    assert len(deliveries) == 2  # No clock/reminder-only pushes.


async def test_dynamic_schedule_adjustment_and_late_dependency(live):
    c, deliveries = live
    await c.async_action("start_bake", {})
    await complete(c, "feed_starter")
    next_due = START + timedelta(hours=4)
    await c.async_action(
        "adjust_step",
        {
            "bake_id": c.bake.id,
            "step_id": "autolyse_start",
            "due_at": next_due.isoformat(),
        },
    )
    assert len(deliveries) == 3
    assert deliveries[-1]["data"]["when"] == int(next_due.timestamp())
    # Completing autolyse late shifts its dependent one-hour timer.
    late = next_due + timedelta(minutes=17)
    await complete(c, "autolyse_start", late)
    assert c.bake.step_runs["autolyse_complete"].due_at == late + timedelta(hours=1)
    assert deliveries[-1]["data"]["tag"] == deliveries[0]["data"]["tag"]
    # The independent starter checkpoint may be due sooner than autolyse.
    assert deliveries[-1]["data"]["progress"] == 2


async def test_pause_resume_and_due_transition(live):
    c, deliveries = live
    await c.async_action("start_bake", {})
    await complete(c, "feed_starter")
    data = {"bake_id": c.bake.id}
    await c.async_action("pause_bake", data)
    assert len(deliveries) == 3
    assert "Paused" in deliveries[-1]["message"]
    assert deliveries[-1]["data"]["chronometer"] is False
    c.clock = lambda: START + timedelta(hours=5)
    await c.async_tick()
    assert len(deliveries) == 3
    await c.async_action("resume_bake", data)
    assert len(deliveries) == 4
    assert "Action due" in deliveries[-1]["message"]
    assert "Paused" not in deliveries[-1]["message"]
    assert deliveries[-1]["data"]["chronometer"] is False


async def test_real_ha_due_timer_updates_once(live, hass, freezer):
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    c, deliveries = live
    freezer.move_to(START)
    c.clock = dt_util.utcnow
    await c.async_action("start_bake", {})
    await complete(c, "feed_starter")
    future = START + timedelta(hours=3)
    freezer.move_to(future)
    async_fire_time_changed(hass, future)
    await hass.async_block_till_done()
    assert len(deliveries) == 3
    assert "Action due" in deliveries[-1]["message"]
    await c.async_tick()
    assert len(deliveries) == 3


@pytest.mark.parametrize("paused", [False, True])
async def test_restart_preserves_identity_and_age(live, hass, paused):
    c, deliveries = live
    await c.async_action("start_bake", {})
    if paused:
        await c.async_action("pause_bake", {"bake_id": c.bake.id})
    tag = deliveries[0]["data"]["tag"]
    count = len(deliveries)
    restored = await restart(c, hass, START + timedelta(hours=2))
    try:
        assert len(deliveries) == count + 1
        assert deliveries[-1]["data"]["tag"] == tag
        assert restored.storage.live_activities[0].started_at == START
        assert restored.live_activities.next_deadline() == START + RENEW_AFTER
        await restored.async_tick()
        assert len(deliveries) == count + 1
    finally:
        await restored.async_shutdown()


@pytest.mark.parametrize("restart_first", [False, True])
async def test_overnight_expiry_renews_same_tag(live, hass, restart_first):
    c, deliveries = live
    await c.async_action("start_bake", {})
    await c.async_action("pause_bake", {"bake_id": c.bake.id})
    tag = deliveries[0]["data"]["tag"]
    future = START + RENEW_AFTER + timedelta(hours=2)
    if restart_first:
        c = await restart(c, hass, future)
    else:
        c.clock = lambda: future
        await c.async_tick()
    try:
        assert deliveries[-2] == {"message": "clear_notification", "data": {"tag": tag}}
        assert deliveries[-1]["data"]["tag"] == tag
        assert c.storage.live_activities[0].started_at == future
        assert c.live_activities.next_deadline() == future + RENEW_AFTER
        assert c.bake.step_runs["feed_starter"].completed_at is None
    finally:
        await c.async_shutdown()


async def test_renewal_is_scheduled_without_polling(live, hass, freezer):
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    c, deliveries = live
    freezer.move_to(START)
    c.clock = dt_util.utcnow
    await c.async_action("start_bake", {})
    await c.async_action("pause_bake", {"bake_id": c.bake.id})
    assert c._cancel_timer is not None
    future = START + RENEW_AFTER
    freezer.move_to(future)
    async_fire_time_changed(hass, future)
    await hass.async_block_till_done()
    assert deliveries[-2]["message"] == "clear_notification"
    assert c.storage.live_activities[0].started_at == future


async def test_completion_clears_and_does_not_restart(live):
    c, deliveries = live
    await c.async_action("start_bake", {})
    for _ in range(30):
        if c.bake.status == BakeStatus.COMPLETED:
            break
        current = c.current_steps()[0]
        await complete(c, current.step_id, max(c.clock(), current.due_at))
    assert c.bake.status == BakeStatus.COMPLETED
    assert deliveries[-1]["message"] == "clear_notification"
    assert c.storage.live_activities == []
    assert c._cancel_timer is None
    count = len(deliveries)
    await c.async_tick()
    assert len(deliveries) == count


async def test_cancellation_and_new_bake_have_distinct_tags(live):
    c, deliveries = live
    await c.async_action("start_bake", {})
    old_tag = deliveries[-1]["data"]["tag"]
    await c.async_action("cancel_bake", {"bake_id": c.bake.id})
    assert deliveries[-1] == {"message": "clear_notification", "data": {"tag": old_tag}}
    assert c.storage.live_activities == []
    assert c._cancel_timer is None
    await c.async_action("start_bake", {})
    assert deliveries[-1]["data"]["tag"] != old_tag


@pytest.mark.parametrize("enabled,target", [(False, TARGET), (True, "")])
async def test_disabled_or_no_phone(live, enabled, target):
    c, deliveries = live
    c.options.update(
        live_activities_enabled=enabled, live_activity_notify_target=target
    )
    await c.async_action("start_bake", {})
    await complete(c, "feed_starter")
    await c.async_action("cancel_bake", {"bake_id": c.bake.id})
    assert deliveries == []
    assert c.live_activities.error is None
    assert c.storage.live_activities == []


@pytest.mark.parametrize(
    "target", ["light.turn_on", "broken", "notify.mobile_app_missing"]
)
async def test_invalid_or_unavailable_target_does_not_break_bake(live, target):
    c, deliveries = live
    c.options["live_activity_notify_target"] = target
    await c.async_action("start_bake", {})
    await complete(c, "feed_starter")
    assert c.bake.step_runs["feed_starter"].finished
    assert c.live_activities.error
    assert c.live_activities.retry_at == START + RETRY_AFTER
    assert c.last_error is None
    assert deliveries == []


async def test_service_appears_late(live, hass):
    c, deliveries = live
    await c.async_start()
    hass.services.async_remove("notify", "mobile_app_live_phone")
    await c.async_action("start_bake", {})
    assert c.live_activities.error

    async def notify(call):
        deliveries.append(dict(call.data))

    hass.services.async_register("notify", "mobile_app_live_phone", notify)
    await hass.async_block_till_done()
    assert len(deliveries) == 1
    assert c.live_activities.error is None


async def test_send_failure_bounded_retry_and_recovery(live, hass):
    c, deliveries = live

    async def fail(call):
        raise HomeAssistantError("phone offline")

    hass.services.async_register("notify", "mobile_app_live_phone", fail)
    await c.async_action("start_bake", {})
    assert "offline" in c.live_activities.error
    assert len(c.storage.live_activities) == 1  # Identity reserved before delivery.
    c.clock = lambda: START + timedelta(minutes=1)
    await c.async_tick()
    assert deliveries == []

    async def notify(call):
        deliveries.append(dict(call.data))

    hass.services.async_register("notify", "mobile_app_live_phone", notify)
    c.clock = lambda: START + RETRY_AFTER
    await c.async_tick()
    assert len(deliveries) == 1
    assert c.live_activities.error is None
    assert c.storage.live_activities[0].started_at == START


async def test_failed_end_survives_restart_and_new_bake(live, hass):
    c, deliveries = live
    await c.async_action("start_bake", {})
    old_tag = deliveries[-1]["data"]["tag"]
    with patch.object(
        c.live_activities, "_send", side_effect=HomeAssistantError("offline")
    ):
        await c.async_action("cancel_bake", {"bake_id": c.bake.id})
        await c.async_action("start_bake", {})
    assert len(c.storage.live_activities) == 2
    restored = await restart(c, hass, START + timedelta(minutes=1))
    try:
        assert deliveries[-2] == {
            "message": "clear_notification",
            "data": {"tag": old_tag},
        }
        assert deliveries[-1]["data"]["tag"] == activity_tag(restored.bake.id)
        assert len(restored.storage.live_activities) == 1
    finally:
        await restored.async_shutdown()


async def test_options_disable_cleans_up_while_regular_reminders_work(live, hass):
    c, deliveries = live
    await c.async_action("start_bake", {})
    restored = await restart(
        c,
        hass,
        START + timedelta(minutes=31),
        {
            "live_activities_enabled": False,
            "live_activity_notify_target": TARGET,
            "notifications_enabled": True,
            "notify_target": TARGET,
        },
    )
    try:
        assert any("actions" in d["data"] for d in deliveries)
        assert deliveries[-1]["message"] == "clear_notification"
        assert deliveries[-1]["data"]["tag"] != next(
            d["data"]["tag"] for d in deliveries if "actions" in d["data"]
        )
        assert restored.storage.live_activities == []
    finally:
        await restored.async_shutdown()


async def test_removed_old_phone_does_not_block_new_target(live, hass):
    c, deliveries = live
    await c.async_action("start_bake", {})
    old_tag = deliveries[-1]["data"]["tag"]
    hass.services.async_remove("notify", "mobile_app_live_phone")
    new_deliveries = []

    async def notify(call):
        new_deliveries.append(dict(call.data))

    hass.services.async_register("notify", "mobile_app_new_phone", notify)
    options = c.options | {"live_activity_notify_target": "notify.mobile_app_new_phone"}
    restored = await restart(c, hass, START + timedelta(minutes=1), options)
    try:
        assert len(new_deliveries) == 1
        assert new_deliveries[-1]["data"]["tag"] == old_tag
        assert len(restored.storage.live_activities) == 2
        assert "cleanup failed" in restored.live_activities.error

        # Restore the old service: only its stale activity is cleared.
        async def old_notify(call):
            deliveries.append(dict(call.data))

        hass.services.async_register("notify", "mobile_app_live_phone", old_notify)
        restored.clock = lambda: START + timedelta(minutes=1) + RETRY_AFTER
        await restored.async_tick()
        assert deliveries[-1]["message"] == "clear_notification"
        assert len(new_deliveries) == 1
        assert len(restored.storage.live_activities) == 1
        assert restored.live_activities.error is None
    finally:
        await restored.async_shutdown()


async def test_enable_during_bake_and_end_recovery(live, hass):
    c, deliveries = live
    c.options["live_activities_enabled"] = False
    await c.async_action("start_bake", {})
    assert deliveries == []
    options = c.options | {"live_activities_enabled": True}
    restored = await restart(c, hass, START + timedelta(hours=1), options)
    try:
        assert len(deliveries) == 1
        assert restored.storage.live_activities[0].started_at == START + timedelta(
            hours=1
        )
        with patch.object(
            restored.live_activities, "_send", side_effect=HomeAssistantError("offline")
        ):
            await restored.async_action("cancel_bake", {"bake_id": restored.bake.id})
        recovered = await restart(restored, hass, START + timedelta(hours=2))
        try:
            assert recovered.bake.status == BakeStatus.CANCELED
            assert deliveries[-1]["message"] == "clear_notification"
            assert recovered.storage.live_activities == []
            assert recovered._cancel_timer is None
        finally:
            await recovered.async_shutdown()
    finally:
        await restored.async_shutdown()


async def test_regular_notification_action_updates_live_activity(live):
    c, deliveries = live
    c.options.update(notifications_enabled=True, notify_target=TARGET)
    await c.async_action("start_bake", {})
    actionable = next(d for d in deliveries if "actions" in d["data"])
    action = actionable["data"]["actions"][0]["action"]
    await c._async_mobile_action(
        Event("mobile_app_notification_action", {"action": action})
    )
    assert updates(deliveries)[-1]["data"]["progress"] == 1
    assert actionable["data"]["tag"] != deliveries[0]["data"]["tag"]


async def test_failed_metadata_save_never_sends_or_undoes_domain_change(live):
    c, deliveries = live
    original = c.storage.async_save

    async def fail_metadata(*args, **kwargs):
        if "live_activities" in kwargs:
            raise OSError("disk full")
        await original(*args, **kwargs)

    with patch.object(c.storage, "async_save", side_effect=fail_metadata):
        await c.async_action("start_bake", {})
    assert c.bake.status == BakeStatus.ACTIVE
    assert c.storage.live_activities == []
    assert deliveries == []
    assert "disk full" in c.live_activities.error


async def test_shutdown_during_metadata_reservation_does_not_send(live):
    c, deliveries = live
    entered, release = asyncio.Event(), asyncio.Event()
    original = c.storage.async_save

    async def slow_metadata(*args, **kwargs):
        if "live_activities" in kwargs:
            entered.set()
            await release.wait()
        await original(*args, **kwargs)

    with patch.object(c.storage, "async_save", side_effect=slow_metadata):
        action = asyncio.create_task(c.async_action("start_bake", {}))
        await entered.wait()
        shutdown = asyncio.create_task(c.async_shutdown())
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(action, shutdown)
    assert deliveries == []
    assert c._cancel_timer is None
