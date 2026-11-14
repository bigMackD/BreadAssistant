"""Companion payloads, durable correlation, dedup, retries, pause and catch-up."""

from datetime import timedelta

import pytest
from homeassistant.core import Event
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bread_assistant.const import DOMAIN
from custom_components.bread_assistant.coordinator import BakeCoordinator
from custom_components.bread_assistant.models import StepStatus

from .test_schedule import START


@pytest.fixture
async def phone(hass, hass_storage):
    deliveries = []

    async def notify(call):
        deliveries.append(call.data)

    hass.services.async_register("notify", "mobile_app_test_phone", notify)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "notify_target": "notify.mobile_app_test_phone",
            "reminder_minutes": 30,
        },
    )
    coordinator = BakeCoordinator(hass, entry, lambda: START)
    await coordinator.async_load()
    await coordinator.async_start()
    yield coordinator, deliveries
    await coordinator.async_shutdown()


def token(deliveries, index=0):
    return deliveries[-1]["data"]["actions"][index]["action"]


async def test_done_duplicate_stale_and_unknown(phone, hass):
    c, deliveries = phone
    await c.async_action("start_bake", {})
    assert len(deliveries) == 1
    action = token(deliveries)
    assert "feed_starter" not in action
    event = Event("mobile_app_notification_action", {"action": action})
    await c._async_mobile_action(event)
    await c._async_mobile_action(event)
    assert c.bake.revision == 1
    assert c.bake.step_runs["feed_starter"].status == StepStatus.DONE
    await c.async_action("cancel_bake", {"bake_id": c.bake.id})
    await c.async_action("start_bake", {})
    await c._async_mobile_action(event)
    await c._async_mobile_action(
        Event("mobile_app_notification_action", {"action": "feed_starter"})
    )
    assert c.bake.step_runs["feed_starter"].completed_at is None
    assert c.bake.revision == 0


async def test_snooze_exactly_ten_minutes_and_stale_generation(phone):
    c, deliveries = phone
    await c.async_action("start_bake", {})
    old_done = token(deliveries)
    await c._async_mobile_action(
        Event("mobile_app_notification_action", {"action": token(deliveries, 1)})
    )
    assert c.bake.step_runs["feed_starter"].due_at == START
    c.clock = lambda: START + timedelta(minutes=9)
    await c.async_tick()
    assert len(deliveries) == 1
    await c._async_mobile_action(
        Event("mobile_app_notification_action", {"action": old_done})
    )
    assert c.bake.step_runs["feed_starter"].completed_at is None
    c.clock = lambda: START + timedelta(minutes=10)
    await c.async_tick()
    await c.async_tick()
    assert len(deliveries) == 2


async def test_capability_survives_restart(phone, hass):
    c, deliveries = phone
    await c.async_action("start_bake", {})
    action = token(deliveries)
    await c.async_shutdown()
    restored = BakeCoordinator(hass, c.entry, lambda: START + timedelta(minutes=1))
    await restored.async_load()
    await restored.async_start()
    assert len(deliveries) == 1
    hass.bus.async_fire("mobile_app_notification_action", {"action": action})
    await hass.async_block_till_done()
    assert restored.bake.step_runs["feed_starter"].status == StepStatus.DONE
    await restored.async_shutdown()


async def test_catchup_pause_missing_phone_and_retry(phone, hass):
    c, deliveries = phone
    await c.async_action("start_bake", {})
    data = {"bake_id": c.bake.id}
    await c.async_action("pause_bake", data)
    c.clock = lambda: START + timedelta(hours=5)
    await c.async_tick()
    assert len(deliveries) == 1
    await c.async_action("resume_bake", data)
    assert len(deliveries) == 2
    assert "catch-up" in deliveries[-1]["title"]
    assert "2 outstanding" in deliveries[-1]["message"]
    hass.services.async_remove("notify", "mobile_app_test_phone")
    c.clock = lambda: START + timedelta(hours=6)
    await c.async_tick()
    assert "unavailable" in c.last_error

    async def unavailable(call):
        raise HomeAssistantError("phone offline")

    hass.services.async_register("notify", "mobile_app_test_phone", unavailable)
    c.clock = lambda: START + timedelta(hours=7)
    await c.async_tick()
    assert "offline" in c.last_error
    assert c._cancel_timer is not None


async def test_disabled_notifications(phone):
    c, deliveries = phone
    c.options["notifications_enabled"] = False
    await c.async_action("start_bake", {})
    assert deliveries == []
