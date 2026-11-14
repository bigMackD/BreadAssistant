"""Config flows and unloaded service behavior."""

import pytest
from homeassistant import data_entry_flow
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bread_assistant.const import DEFAULT_OPTIONS, DOMAIN


async def test_setup_flow_single_instance(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], DEFAULT_OPTIONS
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["reason"] == "already_configured"


async def test_options_and_unloaded_action(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], DEFAULT_OPTIONS | {"notifications_enabled": False}
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(HomeAssistantError, match="not loaded"):
        await hass.services.async_call(DOMAIN, "start_bake", {}, blocking=True)


async def test_live_activity_configuration_and_independent_targets(hass):
    async def notify(call):
        pass

    hass.services.async_register("notify", "mobile_app_iphone", notify)
    hass.services.async_register("notify", "mobile_app_reminders", notify)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    options = DEFAULT_OPTIONS | {
        "live_activities_enabled": True,
        "live_activity_notify_target": "notify.mobile_app_iphone",
        "notifications_enabled": False,
        "notify_target": "notify.mobile_app_reminders",
    }
    result = await hass.config_entries.flow.async_configure(result["flow_id"], options)
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == options


@pytest.mark.parametrize(
    "target", ["light.turn_on", "broken", "notify.mobile_app_removed"]
)
async def test_live_activity_config_rejects_invalid_target(hass, target):
    from custom_components.bread_assistant.config_flow import _errors

    assert _errors(hass, DEFAULT_OPTIONS | {"live_activity_notify_target": target}) == {
        "live_activity_notify_target": "notify_missing"
    }


async def test_options_can_remove_unavailable_live_activity_target(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=DEFAULT_OPTIONS
        | {
            "live_activities_enabled": True,
            "live_activity_notify_target": "notify.mobile_app_removed",
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    # The schema supplies a usable empty default when the old phone was removed.
    values = result["data_schema"]({})
    assert values["live_activity_notify_target"] == ""
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], values
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
