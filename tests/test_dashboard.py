"""Validate native-only YAML, entity references and real HA Jinja rendering."""

from pathlib import Path

import pytest
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


@pytest.mark.parametrize("language", ["en", "pl"])
async def test_dashboard_templates_and_controls(hass, integration, language):
    integration.runtime_data.options["language"] = language
    # The user's sample uses kitchen-prefixed registry IDs. Fixtures use defaults.
    source = Path("dashboards/bread_assistant_native.yaml").read_text(encoding="utf-8")
    dashboard = yaml.safe_load(
        source.replace("kitchen_bread_assistant_", "bread_assistant_")
    )
    await integration.runtime_data.async_action("start_bake", {})
    rendered_cards = []
    for card in cards(dashboard):
        assert not card["type"].startswith("custom:")
        if card["type"] == "markdown":
            rendered = Template(card["content"], hass).async_render()
            assert "TemplateError" not in rendered
            assert "content.recipes." not in rendered
            rendered_cards.append(rendered)
        if "entity" in card:
            assert hass.states.get(card["entity"]) is not None
        if card.get("tap_action", {}).get("perform_action") == "button.press":
            assert hass.states.get(card["tap_action"]["target"]["entity_id"])
    combined = "\n".join(rendered_cards)
    assert ("Harmonogram" if language == "pl" else "Timeline") in combined
    assert ("Dokarm zakwas" if language == "pl" else "Feed starter") in combined
    assert ("Gorące żeliwo" if language == "pl" else "Hot cast iron") in combined


def test_redesigned_dashboard_uses_bundled_card():
    dashboard = yaml.safe_load(
        Path("dashboards/bread_assistant.yaml").read_text(encoding="utf-8")
    )
    view = dashboard["views"][0]
    assert view["path"] == "overview"
    assert view["type"] == "panel"
    assert view["cards"] == [
        {
            "type": "custom:bread-assistant-card",
            "entity_prefix": "kitchen_bread_assistant",
        }
    ]
