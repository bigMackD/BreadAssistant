"""Shared device metadata and lifecycle-safe push subscriptions."""

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import BakeCoordinator


class BreadEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: BakeCoordinator, key: str) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, DOMAIN)},
            name="Bread Assistant",
            manufacturer="Bread Assistant",
            model="Bread Assistant",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        return not self.coordinator.closed

    @property
    def suggested_object_id(self) -> str:
        """Keep the original ID suffix independent of display language."""
        key = self._attr_unique_id.removeprefix(f"{DOMAIN}_")
        return "start_with_prepared_starter" if key == "start_prepared" else key

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._updated))

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()
