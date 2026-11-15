"""Serve the bundled, dependency-free Lovelace card when HTTP is available."""

from pathlib import Path

from homeassistant.core import HomeAssistant

URL_BASE = "/bread_assistant/frontend"
MODULE_URL = f"{URL_BASE}/bread-assistant-card.js?v=1"


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Keep headless installs working; load the card in normal HA frontends."""
    if "http" not in hass.config.components:
        return

    from homeassistant.components.http import StaticPathConfig

    await hass.http.async_register_static_paths(
        [StaticPathConfig(URL_BASE, str(Path(__file__).parent / "frontend"), False)]
    )
    if "frontend" in hass.config.components:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, MODULE_URL)
