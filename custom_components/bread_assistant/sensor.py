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
    SensorEntityDescription(
        key="status",
        translation_key="status",
        icon="mdi:bread-slice",
        device_class=SensorDeviceClass.ENUM,
        options=["idle", "active", "paused", "completed", "canceled"],
    ),
    SensorEntityDescription(key="current_step", translation_key="current_step"),
    SensorEntityDescription(key="next_step", translation_key="next_step"),
    SensorEntityDescription(
        key="next_due",
        translation_key="next_due",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="progress", translation_key="progress", native_unit_of_measurement="%"
    ),
    SensorEntityDescription(key="overdue_count", translation_key="overdue_count"),
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
        return self.coordinator.translator.step(
            bake.recipe_snapshot, steps[index].step_id, "title"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        bake = self.coordinator.bake
        tr = self.coordinator.translator
        key = self.entity_description.key
        if key == "status":
            recipe = (
                bake.recipe_snapshot
                if bake
                else self.coordinator.catalog[DEFAULT_RECIPE]
            )
            return {
                "bake_id": bake.id if bake else None,
                "recipe_title": tr.recipe(recipe, "title", recipe.title),
                "recipe_description": tr.recipe(recipe, "description"),
                "recipe_url": recipe.url,
                "ingredients": [
                    tr.recipe(recipe, f"ingredients.{i}", ingredient)
                    for i, ingredient in enumerate(recipe.ingredients)
                ],
                "starter_id": bake.starter_id if bake else None,
                "starter_workflow": bake.starter_workflow if bake else None,
                "archive_count": len(self.coordinator.archives),
                "last_sync": self.coordinator.last_sync,
                "last_error": self.coordinator.last_error,
                "live_activity_error": self.coordinator.live_activities.error,
                "time_format": self.coordinator.options["time_format"],
                "language": tr.language,
                "ui": tr.section("content.ui"),
                "status_label": tr.text(
                    f"entity.sensor.status.state.{bake.status if bake else 'idle'}"
                ),
                "workflow_label": tr.text(
                    f"selector.starter_workflow.options.{bake.starter_workflow}"
                )
                if bake
                else None,
            }
        if key != "current_step":
            return None
        steps = self.coordinator.current_steps()
        current = steps[0] if steps else None
        now = self.coordinator.clock()
        return {
            "bake_id": bake.id if bake else None,
            "step_id": current.step_id if current else None,
            "instructions": tr.step(
                bake.recipe_snapshot, current.step_id, "instructions"
            )
            if bake and current
            else None,
            "instructions_summary": tr.recipe(
                bake.recipe_snapshot, f"steps.{current.step_id}.summary"
            )
            if bake and current
            else None,
            "confirmation_hint": tr.recipe(
                bake.recipe_snapshot, f"steps.{current.step_id}.confirmation_hint"
            )
            if bake and current
            else None,
            "instructions_attribution": tr.recipe(
                bake.recipe_snapshot, "instructions_attribution"
            )
            if bake and current
            else None,
            "step_status": current.status if current else None,
            "due_at": current.due_at if current else None,
            "snoozed_until": current.snoozed_until if current else None,
            "timeline": [
                {
                    "id": s.id,
                    "title": tr.step(bake.recipe_snapshot, s.id, "title"),
                    "state": bake.step_runs[s.id].status,
                    "state_label": tr.text(
                        f"entity.sensor.current_step.state_attributes.step_status.state.{bake.step_runs[s.id].status}"
                    ),
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
