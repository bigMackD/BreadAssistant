"""Single-instance setup and optional mobile notification destination."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DEFAULT_OPTIONS, DOMAIN
from .notifications import is_mobile_app_target


def _schema(hass: Any, options: dict[str, Any]) -> vol.Schema:
    targets = {"": "No mobile destination"}
    targets.update(
        {
            f"notify.{name}": name
            for name in hass.services.async_services().get("notify", {})
            if name.startswith("mobile_app_")
        }
    )
    return vol.Schema(
        {
            vol.Optional("notify_target", default=options["notify_target"]): vol.In(
                targets
            ),
            vol.Required(
                "notifications_enabled", default=options["notifications_enabled"]
            ): bool,
            vol.Required(
                "live_activities_enabled", default=options["live_activities_enabled"]
            ): bool,
            vol.Optional(
                "live_activity_notify_target",
                default=options["live_activity_notify_target"],
            ): vol.In(targets),
            vol.Required(
                "reminder_minutes", default=options["reminder_minutes"]
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=240)),
            vol.Required(
                "dashboard_path", default=options["dashboard_path"]
            ): vol.Match(r"^/[a-zA-Z0-9_/-]+$"),
            vol.Required("time_format", default=options["time_format"]): vol.In(
                ["24h", "12h"]
            ),
        }
    )


def _errors(hass: Any, data: dict[str, Any]) -> dict[str, str]:
    for key in ("notify_target", "live_activity_notify_target"):
        target = data.get(key, "")
        if target and (
            not is_mobile_app_target(target)
            or not hass.services.has_service(*target.split(".", 1))
        ):
            return {key: "notify_missing"}
    return {}


class BreadAssistantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up the local baking assistant."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors = _errors(self.hass, user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            return self.async_create_entry(title="Bread Assistant", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(self.hass, DEFAULT_OPTIONS),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> Any:
        return BreadAssistantOptionsFlow()


class BreadAssistantOptionsFlow(config_entries.OptionsFlow):
    """Change notification and display preferences without recreating a bake."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        options = DEFAULT_OPTIONS | self.config_entry.data | self.config_entry.options
        # A removed phone must not prevent opening and saving the options form.
        for key in ("notify_target", "live_activity_notify_target"):
            if options[key] and (
                not is_mobile_app_target(options[key])
                or not self.hass.services.has_service(*options[key].split(".", 1))
            ):
                options[key] = ""
        errors = _errors(self.hass, user_input) if user_input is not None else {}
        if user_input is not None and not errors:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(self.hass, options),
            errors=errors,
        )
