"""Home Assistant owns atomic storage; never write directly to .storage."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .models import BakeRun, DomainError, LiveActivity
from .serialization import (
    SCHEMA_VERSION,
    bake_from_dict,
    bake_to_dict,
    live_activities_from_dict,
    live_activities_to_dict,
    migrate_payload,
)


class BreadStore(Store[dict[str, Any]]):
    """Migrate old snapshots without requiring Starter Manager."""

    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict[str, Any]
    ) -> dict[str, Any]:
        return migrate_payload(old_data, old_major_version)


class BakeStorage:
    def __init__(self, hass: HomeAssistant) -> None:
        self.live_activities: list[LiveActivity] = []
        self.store = BreadStore(
            hass, SCHEMA_VERSION, f"{DOMAIN}.bakes", private=True, atomic_writes=True
        )

    async def async_load(self) -> tuple[BakeRun | None, list[dict[str, Any]]]:
        payload = await self.store.async_load()
        if payload is None:
            return None, []
        if not isinstance(payload, dict):
            raise DomainError("Storage payload must be an object")
        payload = migrate_payload(payload, payload.get("schema_version", 1))
        self.live_activities = live_activities_from_dict(
            payload.get("live_activities", [])
        )
        archives = payload.get("archives", [])
        if not isinstance(archives, list) or any(
            not isinstance(a, dict) for a in archives
        ):
            raise DomainError("Invalid archive summaries")
        bake = bake_from_dict(payload["bake"]) if payload.get("bake") else None
        return bake, archives[-50:]

    async def async_save(
        self,
        bake: BakeRun | None,
        archives: list[dict[str, Any]],
        *,
        live_activities: list[LiveActivity] | None = None,
    ) -> None:
        records = self.live_activities if live_activities is None else live_activities
        await self.store.async_save(
            {
                "schema_version": SCHEMA_VERSION,
                "bake": bake_to_dict(bake) if bake else None,
                "archives": archives[-50:],
                "live_activities": live_activities_to_dict(records),
            }
        )
        self.live_activities = records
