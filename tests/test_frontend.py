"""The packaged card is available without a theme, plugins or frontend runtime."""

from unittest.mock import AsyncMock, patch

from custom_components.bread_assistant.frontend import (
    MODULE_URL,
    URL_BASE,
    async_setup_frontend,
)


async def test_headless_setup(hass):
    await async_setup_frontend(hass)


async def test_static_assets_and_module_registration(hass, hass_client):
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "http", {})
    # Simulate an already initialized frontend without loading its panels.
    hass.config.components.add("frontend")
    with patch("homeassistant.components.frontend.add_extra_js_url") as add_module:
        await async_setup_frontend(hass)
    add_module.assert_called_once_with(hass, MODULE_URL)
    client = await hass_client()
    for filename in ["bread-assistant-card.js", "styles.js", "strings.js"]:
        response = await client.get(f"{URL_BASE}/{filename}")
        assert response.status == 200
        assert "javascript" in response.headers["Content-Type"]
        assert len(await response.text()) > 100
    response = await client.get(f"{URL_BASE}/../manifest.json")
    assert response.status == 404


async def test_http_without_frontend(hass):
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "http", {})
    with (
        patch.object(
            hass.http, "async_register_static_paths", new=AsyncMock()
        ) as serve,
        patch("homeassistant.components.frontend.add_extra_js_url") as add_module,
    ):
        await async_setup_frontend(hass)
    serve.assert_awaited_once()
    add_module.assert_not_called()


async def test_real_frontend_loads_card_once_across_entry_reload(
    hass, hass_storage, tmp_path
):
    from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.bread_assistant.const import DOMAIN

    # The backend test image omits HA's large browser asset wheel. Supply only
    # its static root; the frontend lifecycle/module loader still runs for real.
    with patch(
        "homeassistant.components.frontend._frontend_root", return_value=tmp_path
    ):
        assert await async_setup_component(hass, "frontend", {})
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert MODULE_URL in hass.data[DATA_EXTRA_MODULE_URL].urls
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert list(hass.data[DATA_EXTRA_MODULE_URL].urls).count(MODULE_URL) == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
