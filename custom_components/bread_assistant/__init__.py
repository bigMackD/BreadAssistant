"""Home Assistant adapter for the local Bread Assistant engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, PLATFORMS, SERVICES
from .i18n import load_translations


def action_error(error: Exception) -> Any:
    """Expose domain keys to HA so each frontend can translate the failure."""
    from homeassistant.exceptions import HomeAssistantError

    from .i18n import Translator

    key = getattr(error, "translation_key", "invalid_action")
    placeholders = {
        key: Translator().error(value) if isinstance(value, Exception) else str(value)
        for key, value in getattr(error, "placeholders", {}).items()
    }
    return HomeAssistantError(
        Translator().error(error)
        if hasattr(error, "translation_key")
        else Translator().text("exceptions.invalid_action.message"),
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders,
    )


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register the canonical API even when the config entry is unloaded."""
    import voluptuous as vol
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.helpers import config_validation as cv

    hass.data.setdefault(DOMAIN, {})
    await hass.async_add_executor_job(load_translations)
    from .frontend import async_setup_frontend

    await async_setup_frontend(hass)
    identity = {vol.Required("bake_id"): cv.string}
    step = identity | {vol.Required("step_id"): cv.string}
    schemas = {
        "start_bake": vol.Schema(
            {
                vol.Optional("recipe_id"): cv.string,
                vol.Optional("start_time"): cv.string,
                vol.Optional("starter_id"): cv.string,
                vol.Optional("starter_workflow", default="feed"): vol.In(
                    ["feed", "prepared"]
                ),
                vol.Optional("starter_ready", default=False): cv.boolean,
            }
        ),
        "complete_step": vol.Schema(step),
        "snooze_step": vol.Schema(
            step
            | {
                vol.Required("minutes"): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=1440)
                )
            }
        ),
        "adjust_step": vol.Schema(step | {vol.Required("due_at"): cv.string}),
        **{
            name: vol.Schema(identity)
            for name in ("pause_bake", "resume_bake", "cancel_bake")
        },
    }

    async def handle(call: ServiceCall) -> None:
        coordinator = hass.data[DOMAIN].get("coordinator")
        if coordinator is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="not_loaded"
            )
        try:
            await coordinator.async_action(call.service, dict(call.data))
        except (ValueError, KeyError) as err:
            raise action_error(err) from err

    for name in SERVICES:
        hass.services.async_register(DOMAIN, name, handle, schema=schemas[name])
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Restore persistent state before forwarding entity platforms."""
    from .coordinator import BakeCoordinator

    coordinator = BakeCoordinator(hass, entry)
    await coordinator.async_load()
    hass.data[DOMAIN]["coordinator"] = coordinator
    entry.runtime_data = coordinator
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        await coordinator.async_start()
    except Exception:
        await coordinator.async_shutdown()
        hass.data[DOMAIN].pop("coordinator", None)
        raise
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Cancel runtime work only after platforms successfully unload."""
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
        hass.data[DOMAIN].pop("coordinator", None)
        return True
    return False
