"""Native controls that capture explicit bake/step identity at press time."""

from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import action_error
from .entity import BreadEntity
from .models import BakeStatus

DESCRIPTIONS = (
    ButtonEntityDescription(
        key="start", translation_key="start", icon="mdi:bread-slice"
    ),
    ButtonEntityDescription(key="start_prepared", translation_key="start_prepared"),
    ButtonEntityDescription(key="complete_current", translation_key="complete_current"),
    ButtonEntityDescription(key="snooze_current", translation_key="snooze_current"),
    ButtonEntityDescription(key="pause", translation_key="pause"),
    ButtonEntityDescription(key="resume", translation_key="resume"),
    ButtonEntityDescription(key="cancel", translation_key="cancel"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(BreadButton(entry.runtime_data, d) for d in DESCRIPTIONS)


class BreadButton(BreadEntity, ButtonEntity):
    def __init__(self, coordinator: Any, description: ButtonEntityDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        bake = self.coordinator.bake
        status = bake.status if bake else None
        key = self.entity_description.key
        if key in ("start", "start_prepared"):
            return status not in (BakeStatus.ACTIVE, BakeStatus.PAUSED)
        if key == "resume":
            return status == BakeStatus.PAUSED
        if key == "cancel":
            return status in (BakeStatus.ACTIVE, BakeStatus.PAUSED)
        if key == "pause":
            return status == BakeStatus.ACTIVE
        if status != BakeStatus.ACTIVE:
            return False
        steps = self.coordinator.current_steps()
        if key == "complete_current":
            return bool(steps)
        return bool(steps and steps[0].due_at <= self.coordinator.clock())

    async def async_press(self) -> None:
        if not self.available:
            raise HomeAssistantError(
                translation_domain="bread_assistant",
                translation_key="control_unavailable",
            )
        key = self.entity_description.key
        data: dict[str, Any] = {}
        if key in ("start", "start_prepared"):
            action = "start_bake"
            data["starter_workflow"] = "prepared" if key == "start_prepared" else "feed"
        else:
            data["bake_id"] = self.coordinator.bake.id
            if key in ("complete_current", "snooze_current"):
                data["step_id"] = self.coordinator.current_steps()[0].step_id
                action = "complete_step" if key == "complete_current" else "snooze_step"
                if key == "snooze_current":
                    data["minutes"] = 10
            else:
                action = f"{key}_bake"
        try:
            await self.coordinator.async_action(action, data)
        except ValueError as err:
            raise action_error(err) from err
