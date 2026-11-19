"""Export real sensor presentations for isolated browser tests; no HA server needed."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import yaml

from custom_components.bread_assistant import scheduler
from custom_components.bread_assistant.const import DEFAULT_RECIPE
from custom_components.bread_assistant.i18n import Translator
from custom_components.bread_assistant.recipe_catalog import load_catalog
from custom_components.bread_assistant.sensor import DESCRIPTIONS, BreadSensor

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)
catalog = load_catalog()
recipe = catalog[DEFAULT_RECIPE]


def presentation(bake, language, error=None):
    coordinator = SimpleNamespace(
        bake=bake,
        translator=Translator(language),
        catalog=catalog,
        archives=[],
        clock=lambda: NOW,
        current_steps=lambda: scheduler.actionable(bake, include_paused=True)
        if bake
        else [],
        options={"time_format": "24h"},
        last_sync=NOW.isoformat(),
        last_error=error,
        live_activities=SimpleNamespace(error=None),
    )
    result = {}
    for description in DESCRIPTIONS:
        sensor = BreadSensor(coordinator, description)
        value = sensor.native_value
        result[f"sensor.bread_assistant_{description.key}"] = {
            "state": "unknown" if value is None else str(value),
            "attributes": sensor.extra_state_attributes or {},
        }
    return result


def advance_to(step_id, started_at=NOW - timedelta(hours=22)):
    bake = scheduler.create_bake(recipe, started_at)
    while True:
        current = scheduler.actionable(bake)[0]
        if current.step_id == step_id:
            return bake
        scheduler.complete(bake, current.step_id, current.due_at)


scenarios = {}
stage_scenarios = {}
for language in ["en", "pl"]:
    due = scheduler.create_bake(recipe, NOW)
    waiting = scheduler.create_bake(recipe, NOW - timedelta(minutes=30))
    scheduler.complete(waiting, "feed_starter", NOW - timedelta(minutes=30))
    overdue = scheduler.create_bake(recipe, NOW - timedelta(minutes=17))
    snoozed = deepcopy(overdue)
    scheduler.snooze(snoozed, "feed_starter", 10, NOW)
    paused = deepcopy(waiting)
    scheduler.lifecycle(paused, "pause_bake", NOW)
    canceled = deepcopy(waiting)
    scheduler.lifecycle(canceled, "cancel_bake", NOW)
    completed = advance_to("cooling_check")
    scheduler.complete(completed, "cooling_check", NOW)
    prepared = scheduler.create_bake(recipe, NOW, starter_workflow="prepared")
    parallel = deepcopy(waiting)
    scheduler.complete(parallel, "autolyse_start", NOW - timedelta(minutes=15))
    overnight = advance_to("preheat_oven", NOW - timedelta(hours=16))
    preheating = deepcopy(overnight)
    scheduler.complete(preheating, "preheat_oven", NOW)
    scenarios[language] = {
        name: presentation(bake, language)
        for name, bake in {
            "idle": None,
            "active": waiting,
            "due": due,
            "overdue": overdue,
            "snoozed": snoozed,
            "paused": paused,
            "completed": completed,
            "canceled": canceled,
            "prepared": prepared,
            "cold_proof": advance_to("preheat_oven"),
            "parallel": parallel,
            "overnight": overnight,
            "preheating": preheating,
        }.items()
    }
    scenarios[language]["error"] = presentation(
        waiting,
        language,
        Translator(language).text("exceptions.mobile_unavailable.message"),
    )
    scenarios[language]["unavailable"] = {
        "sensor.bread_assistant_status": {"state": "unavailable", "attributes": {}}
    }
    scenarios[language]["disconnected"] = presentation(overdue, language)
    stage_scenarios[language] = {
        step.id: presentation(advance_to(step.id), language) for step in recipe.steps
    }

reference = yaml.safe_load(
    Path("docs/design-reference/maciek_ios/maciek_ios.yaml").read_text("utf-8")
)
output = Path("test-results/frontend")
output.mkdir(parents=True, exist_ok=True)
(output / "fixtures.json").write_text(
    json.dumps(
        {
            "now": NOW.isoformat(),
            "scenarios": scenarios,
            "stage_scenarios": stage_scenarios,
            "reference_theme": reference["Maciek iOS"]["modes"]["dark"],
        },
        ensure_ascii=False,
        default=str,
    ),
    encoding="utf-8",
)
print(f"Exported {sum(map(len, scenarios.values()))} localized sensor scenarios.")
