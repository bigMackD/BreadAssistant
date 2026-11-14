"""Bounded timeline, diagnostic state and timestamp entities without polling."""

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_RECIPE
from .entity import BreadEntity

DESCRIPTIONS = (
    SensorEntityDescription(key="status", name="Status", icon="mdi:bread-slice"),
    SensorEntityDescription(key="current_step", name="Current step"),
    SensorEntityDescription(key="next_step", name="Next step"),
    SensorEntityDescription(
        key="next_due", name="Next due", device_class=SensorDeviceClass.TIMESTAMP
    ),
    SensorEntityDescription(
        key="progress", name="Progress", native_unit_of_measurement="%"
    ),
    SensorEntityDescription(key="overdue_count", name="Overdue count"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(BreadSensor(entry.runtime_data, d) for d in DESCRIPTIONS)


class BreadSensor(BreadEntity, SensorEntity):
    def __init__(self, coordinator: Any, description: SensorEntityDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | float | datetime | None:
        bake = self.coordinator.bake
        key = self.entity_description.key
        steps = self.coordinator.current_steps()
        if key == "status":
            return bake.status if bake else "idle"
        if key == "progress":
            if not bake:
                return 0
            required = [
                bake.step_runs[s.id]
                for s in bake.recipe_snapshot.steps
                if not s.optional
            ]
            return round(100 * sum(r.finished for r in required) / len(required), 1)
        if key == "overdue_count":
            return sum(r.due_at < self.coordinator.clock() for r in steps)
        if key == "next_due":
            return steps[0].due_at if steps else None
        index = 1 if key == "next_step" else 0
        if not bake or len(steps) <= index:
            return None
        return bake.recipe_snapshot.by_id[steps[index].step_id].title

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        bake = self.coordinator.bake
        key = self.entity_description.key
        if key == "status":
            recipe = (
                bake.recipe_snapshot
                if bake
                else self.coordinator.catalog[DEFAULT_RECIPE]
            )
            return {
                "bake_id": bake.id if bake else None,
                "recipe_title": recipe.title,
                "recipe_url": recipe.url,
                "ingredients": list(recipe.ingredients),
                "starter_id": bake.starter_id if bake else None,
                "starter_workflow": bake.starter_workflow if bake else None,
                "archive_count": len(self.coordinator.archives),
                "last_sync": self.coordinator.last_sync,
                "last_error": self.coordinator.last_error,
                "live_activity_error": self.coordinator.live_activities.error,
                "time_format": self.coordinator.options["time_format"],
            }
        if key != "current_step":
            return None
        steps = self.coordinator.current_steps()
        current = steps[0] if steps else None
        now = self.coordinator.clock()
        return {
            "bake_id": bake.id if bake else None,
            "step_id": current.step_id if current else None,
            "instructions": bake.recipe_snapshot.by_id[current.step_id].instructions
            if bake and current
            else None,
            "step_status": current.status if current else None,
            "due_at": current.due_at if current else None,
            "snoozed_until": current.snoozed_until if current else None,
            "timeline": [
                {
                    "id": s.id,
                    "title": s.title,
                    "state": bake.step_runs[s.id].status,
                    "planned_at": bake.step_runs[s.id].planned_at.isoformat(),
                    "due_at": bake.step_runs[s.id].due_at.isoformat(),
                    "completed_at": bake.step_runs[s.id].completed_at.isoformat()
                    if bake.step_runs[s.id].completed_at
                    else None,
                    "reference": s.reference,
                    "overdue": not bake.step_runs[s.id].finished
                    and bake.step_runs[s.id].due_at < now,
                }
                for s in bake.recipe_snapshot.steps[:24]
            ]
            if bake
            else [],
        }
