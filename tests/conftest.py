"""Tests use real HA fixtures and never connect to a live instance."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bread_assistant.const import DOMAIN

from .test_schedule import START


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Allow the local integration to load."""


@pytest.fixture
async def integration(hass, hass_storage):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entry.runtime_data.clock = lambda: START
    yield entry
    if hasattr(entry, "runtime_data") and not entry.runtime_data.closed:
        assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
