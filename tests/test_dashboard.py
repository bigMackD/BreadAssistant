"""Validate native-only YAML, entity references and real HA Jinja rendering."""

from pathlib import Path

import yaml
from homeassistant.helpers.template import Template


def cards(value):
    if isinstance(value, dict):
        if "type" in value:
            yield value
        for child in value.values():
            yield from cards(child)
    elif isinstance(value, list):
        for child in value:
            yield from cards(child)


async def test_dashboard_templates_and_controls(hass, integration):
    dashboard = yaml.safe_load(Path("dashboards/bread_assistant.yaml").read_text())
    await integration.runtime_data.async_action("start_bake", {})
    for card in cards(dashboard):
        assert not card["type"].startswith("custom:")
        if card["type"] == "markdown":
            rendered = Template(card["content"], hass).async_render()
            assert "TemplateError" not in rendered
        if "entity" in card:
            assert hass.states.get(card["entity"]) is not None
        if card.get("tap_action", {}).get("perform_action") == "button.press":
            assert hass.states.get(card["tap_action"]["target"]["entity_id"])
