"""Real HA entry lifecycle, entity controls, action schemas and stale identities."""

from datetime import timedelta

import pytest
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError

from custom_components.bread_assistant.const import DOMAIN

from .test_schedule import START


async def test_entry_entities_actions_and_teardown(hass, integration):
    assert hass.bus.async_listeners().get("mobile_app_notification_action") == 1
    assert hass.states.get("sensor.bread_assistant_status").state == "idle"
    await hass.services.async_call(DOMAIN, "start_bake", {}, blocking=True)
    assert hass.states.get("sensor.bread_assistant_status").state == "active"
    bake_id = integration.runtime_data.bake.id
    await hass.services.async_call(
        DOMAIN,
        "complete_step",
        {
            "bake_id": bake_id,
            "step_id": "feed_starter",
        },
        blocking=True,
    )
    current = hass.states.get("sensor.bread_assistant_current_step")
    assert current.attributes["step_id"] == "autolyse_start"
    assert len(current.attributes["timeline"]) == 21
    assert hass.states.get("sensor.bread_assistant_progress").state == "5.0"
    runtime = integration.runtime_data
    assert await hass.config_entries.async_unload(integration.entry_id)
    assert runtime.closed
    assert runtime._cancel_timer is None
    assert not runtime._listeners
    assert hass.bus.async_listeners().get("mobile_app_notification_action", 0) == 0
    assert await hass.config_entries.async_setup(integration.entry_id)
    await hass.async_block_till_done()
    assert integration.runtime_data.bake.id == bake_id
    assert hass.bus.async_listeners().get("mobile_app_notification_action") == 1


async def test_native_lifecycle_and_snooze_controls(hass, integration):
    async def press(key):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": f"button.bread_assistant_{key}"},
            blocking=True,
        )

    await press("start")
    await press("snooze_current")
    assert integration.runtime_data.bake.step_runs["feed_starter"].snoozed_until
    await press("pause")
    assert (
        hass.states.get("sensor.bread_assistant_current_step").state == "Feed starter"
    )
    assert (
        hass.states.get("button.bread_assistant_complete_current").state
        == "unavailable"
    )
    await press("resume")
    await press("cancel")
    assert hass.states.get("sensor.bread_assistant_status").state == "canceled"


async def test_validation_and_unknown_actions(hass, integration):
    await hass.services.async_call(DOMAIN, "start_bake", {}, blocking=True)
    coordinator = integration.runtime_data
    data = {"bake_id": coordinator.bake.id, "step_id": "feed_starter"}
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "snooze_step", data | {"minutes": -1}, blocking=True
        )
    with pytest.raises(HomeAssistantError, match="stale"):
        await hass.services.async_call(
            DOMAIN, "complete_step", data | {"bake_id": "old"}, blocking=True
        )
    with pytest.raises(HomeAssistantError, match="Unknown step"):
        await hass.services.async_call(
            DOMAIN, "complete_step", data | {"step_id": "wrong"}, blocking=True
        )
    with pytest.raises(HomeAssistantError, match="timezone"):
        await hass.services.async_call(
            DOMAIN,
            "adjust_step",
            data | {"due_at": "2026-11-14T11:00:00"},
            blocking=True,
        )


async def test_native_prepared_and_complete_buttons(hass, integration):
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.bread_assistant_start_with_prepared_starter"},
        blocking=True,
    )
    assert integration.runtime_data.bake.starter_workflow == "prepared"
    assert integration.runtime_data.bake.step_runs["starter_ready"].completed_at is None
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.bread_assistant_complete_current"},
        blocking=True,
    )
    integration.runtime_data.clock = lambda: START + timedelta(hours=1)
    await integration.runtime_data.async_tick()
    assert (
        hass.states.get("button.bread_assistant_complete_current").state
        != "unavailable"
    )
