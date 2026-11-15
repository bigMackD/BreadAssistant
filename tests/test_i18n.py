"""Translation contracts, HA localization, and unchanged bake data across languages."""

import ast
import json
from copy import deepcopy
from dataclasses import replace
from string import Formatter

import pytest
import yaml
from homeassistant.core import Event
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.translation import async_get_translations
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bread_assistant import action_error
from custom_components.bread_assistant.const import DEFAULT_OPTIONS, DOMAIN
from custom_components.bread_assistant.i18n import (
    ROOT,
    Translator,
    load_bundle,
    resolve_language,
)
from custom_components.bread_assistant.live_activities import activity_payload
from custom_components.bread_assistant.models import DomainError
from custom_components.bread_assistant.notifications import prepare_notification
from custom_components.bread_assistant.recipe_catalog import load_catalog
from custom_components.bread_assistant.scheduler import create_bake
from custom_components.bread_assistant.serialization import bake_to_dict

from .test_schedule import START


def leaves(value, prefix=""):
    result = {}
    for name, child in value.items():
        key = f"{prefix}.{name}" if prefix else name
        if isinstance(child, dict):
            result.update(leaves(child, key))
        else:
            assert isinstance(child, str) and child.strip(), key
            result[key] = child
    return result


def fields(value):
    return {name for _, name, _, _ in Formatter().parse(value) if name is not None}


@pytest.mark.parametrize("directory", ["translations", "localization"])
def test_translation_completeness_and_placeholders(directory):
    def read(language):
        return json.loads((ROOT / directory / f"{language}.json").read_text("utf-8"))

    english, polish = leaves(read("en")), leaves(read("pl"))
    assert english.keys() == polish.keys()
    for key, value in english.items():
        assert fields(value) == fields(polish[key]), key
        assert "[%key:" not in value
    if directory == "translations":
        assert read("en") == json.loads((ROOT / "strings.json").read_text("utf-8"))


@pytest.mark.parametrize(
    ("preference", "system", "expected"),
    [
        ("auto", "en", "en"),
        ("auto", "pl", "pl"),
        ("auto", "pl-PL", "pl"),
        ("auto", "en_US", "en"),
        ("auto", "de", "en"),
        ("pl", "en", "pl"),
        ("en", "pl", "en"),
        ("de", "pl", "en"),
    ],
)
def test_language_selection(preference, system, expected):
    assert resolve_language(preference, system) == expected


def test_missing_key_and_invalid_placeholders_fall_back(monkeypatch):
    bundle = deepcopy(load_bundle("pl"))
    bundle["content"]["ui"].pop("timeline")
    bundle["content"]["notifications"]["done"] = "Gotowe: {wrong}"
    english = load_bundle("en")
    monkeypatch.setattr(
        "custom_components.bread_assistant.i18n.load_bundle",
        lambda language: bundle if language == "pl" else english,
    )
    tr = Translator("pl")
    assert tr.text("content.ui.timeline") == "Timeline"
    assert tr.section("content.ui")["timeline"] == "Timeline"
    assert tr.text("content.notifications.done", title="test") == "Done: test"
    assert tr.text("missing", fallback="Legacy") == "Legacy"
    assert tr.text("missing") == "missing"
    bundle["content"]["notifications"]["done"] = "Błędny {"
    assert tr.text("content.notifications.done", title="test") == "Done: test"


@pytest.mark.parametrize("language", ["en", "pl"])
def test_recipe_content_and_notification_payloads(language):
    tr = Translator(language)
    recipe = next(iter(load_catalog().values()))
    bake = create_bake(recipe, START)
    title = "Dokarm zakwas" if language == "pl" else "Feed starter"
    assert tr.step(recipe, "feed_starter", "title") == title
    assert "content." not in tr.recipe(recipe, "title", recipe.title)
    assert tr.recipe(recipe, "description")
    for index, ingredient in enumerate(recipe.ingredients):
        assert tr.recipe(recipe, f"ingredients.{index}", ingredient) != ingredient
    for step in recipe.steps:
        for field in ("title", "instructions"):
            assert tr.step(recipe, step.id, field) != getattr(step, field)
    original = bake_to_dict(bake)
    payload = prepare_notification(bake, ["feed_starter"], False, "/bread", tr)
    assert title in payload["title"]
    assert title in payload["data"]["actions"][0]["title"]
    assert payload["data"]["actions"][1]["title"] == tr.text(
        "content.notifications.snooze"
    )
    catchup = prepare_notification(
        bake, ["preheat_oven", "oven_ready"], True, "/bread", tr
    )
    assert tr.text("content.notifications.catchup") in catchup["title"]
    assert tr.text("content.notifications.hot") in catchup["message"]
    live = activity_payload(bake, START, "/bread", tr)
    assert title == live["data"]["critical_text"]
    assert tr.text("content.live.due") in live["message"]
    # Translation may reserve capabilities, but never changes the domain snapshot.
    assert bake_to_dict(bake)["recipe_snapshot"] == original["recipe_snapshot"]
    assert bake_to_dict(bake)["step_runs"] == original["step_runs"]


def test_legacy_snapshots_and_unbundled_recipes():
    recipe = next(iter(load_catalog().values()))
    english = Translator()
    legacy = replace(
        recipe,
        title=english.recipe(recipe, "title"),
        steps=tuple(
            replace(
                s,
                title=english.step(recipe, s.id, "title"),
                instructions=english.step(recipe, s.id, "instructions"),
            )
            for s in recipe.steps
        ),
    )
    assert Translator("pl").step(legacy, "feed_starter", "title") == "Dokarm zakwas"
    unknown = replace(legacy, id="custom_recipe")
    assert Translator("pl").step(unknown, "feed_starter", "title") == "Feed starter"


def test_all_runtime_literal_keys_and_domain_error_keys_exist():
    english = leaves(load_bundle("en"))
    for path in ROOT.glob("*.py"):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            first = node.args[0]
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                continue
            if isinstance(node.func, ast.Name) and node.func.id == "DomainError":
                assert f"exceptions.{first.value}.message" in english, path
            if isinstance(node.func, ast.Attribute) and node.func.attr == "text":
                assert first.value in english, (path, first.value)
    for recipe in load_catalog().values():
        for step in recipe.steps:
            assert step.title in english
            assert step.instructions in english
        assert recipe.title in english
        assert all(ingredient in english for ingredient in recipe.ingredients)


def test_native_service_and_selector_keys_complete():
    services = yaml.safe_load((ROOT / "services.yaml").read_text("utf-8"))
    native = load_bundle("en")
    for name, service in services.items():
        translated = native["services"][name]
        assert translated["name"] and translated["description"]
        assert set(translated["fields"]) == set(service["fields"])
        assert all(field["name"] for field in translated["fields"].values())
    assert set(native["selector"]["language"]["options"]) == {"auto", "en", "pl"}


@pytest.mark.parametrize("language", ["en", "pl"])
async def test_home_assistant_native_translation_loader(hass, integration, language):
    for category, key in [
        ("entity", "entity.sensor.status.state.active"),
        ("services", "services.start_bake.name"),
        ("selector", "selector.language.options.auto"),
        ("exceptions", "exceptions.stale_bake.message"),
        ("options", "options.step.init.data.language"),
    ]:
        translations = await async_get_translations(hass, language, category, {DOMAIN})
        assert translations[f"component.{DOMAIN}.{key}"] == Translator(language).text(
            key
        )


async def test_localized_service_errors_keep_native_metadata(hass, integration):
    with pytest.raises(HomeAssistantError) as caught:
        await hass.services.async_call(
            DOMAIN,
            "complete_step",
            {"bake_id": "old", "step_id": "feed_starter"},
            blocking=True,
        )
    assert caught.value.translation_key == "stale_bake"
    assert caught.value.translation_domain == DOMAIN
    assert (
        Translator("pl").error(DomainError("stale_bake"))
        == "Nieznany lub nieaktualny identyfikator wypieku"
    )
    assert action_error(DomainError("too_early")).translation_key == "too_early"


async def test_language_options_preserve_active_bake(hass, integration, freezer):
    freezer.move_to(START)
    c = integration.runtime_data
    await c.async_action("start_bake", {})
    await c.async_action(
        "complete_step", {"bake_id": c.bake.id, "step_id": "feed_starter"}
    )
    before = bake_to_dict(c.bake)
    entity_ids = {
        state.entity_id
        for state in hass.states.async_all()
        if "bread_assistant" in state.entity_id
    }
    for language in ["pl", "en"]:
        flow = await hass.config_entries.options.async_init(integration.entry_id)
        await hass.config_entries.options.async_configure(
            flow["flow_id"], DEFAULT_OPTIONS | {"language": language}
        )
        await hass.async_block_till_done()
        c = integration.runtime_data
        assert bake_to_dict(c.bake) == before
        status = hass.states.get("sensor.bread_assistant_status")
        assert status.state == "active"
        assert status.attributes["language"] == language
        assert hass.states.get("sensor.bread_assistant_current_step").state == (
            "Rozpocznij autolizę" if language == "pl" else "Start autolyse"
        )
        assert entity_ids == {
            state.entity_id
            for state in hass.states.async_all()
            if "bread_assistant" in state.entity_id
        }


async def test_auto_language_change_refreshes_presentation_only(hass, integration):
    c = integration.runtime_data
    await c.async_action("start_bake", {})
    before = bake_to_dict(c.bake)
    await hass.config.async_update(language="pl")
    await hass.async_block_till_done()
    assert (
        hass.states.get("sensor.bread_assistant_current_step").state == "Dokarm zakwas"
    )
    assert bake_to_dict(c.bake) == before
    c.options["language"] = "en"
    await c._async_language_updated(Event("core_config_updated"))
    assert c.translator.language == "en"


async def test_first_setup_in_polish_preserves_entity_ids(hass, hass_storage):
    await hass.config.async_update(language="pl")
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bread_assistant_status").state == "idle"
    assert hass.states.get("button.bread_assistant_start")
    assert hass.states.get("button.bread_assistant_start_with_prepared_starter")
    assert hass.states.get("button.bread_assistant_start").name.endswith(
        "Dokarm zakwas"
    )
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_diagnostics_relocalize_without_mutating_bake(hass, integration):
    c = integration.runtime_data
    await c.async_action("start_bake", {})
    before = bake_to_dict(c.bake)
    c._last_error = ("reminder", DomainError("mobile_unavailable"))
    assert "unavailable" in c.last_error
    c.options["language"] = "pl"
    assert "niedostępne" in c.last_error
    assert "Nie udało się dostarczyć" in c.last_error
    assert bake_to_dict(c.bake) == before
