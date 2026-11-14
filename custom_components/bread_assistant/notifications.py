"""Companion payloads and opaque, persisted action capabilities."""

import re
import secrets
from typing import Any

from .models import BakeRun


def is_mobile_app_target(target: Any) -> bool:
    """Never dispatch to arbitrary HA services from notification configuration."""
    return isinstance(target, str) and bool(
        re.fullmatch(r"notify\.mobile_app_[a-z0-9_]+", target)
    )


def prepare_notification(
    bake: BakeRun,
    step_ids: list[str],
    catchup: bool,
    dashboard_path: str,
) -> dict[str, Any]:
    """Buttons target the first listed step; a summary never completes a group."""
    first = step_ids[0]
    run = bake.step_runs[first]
    bake.notification_actions = {
        token: value
        for token, value in bake.notification_actions.items()
        if value["step_id"] not in step_ids
    }
    actions = []
    title = bake.recipe_snapshot.by_id[first].title
    for action, label in (("done", f"Done: {title}"), ("snooze", "Remind in 10 min")):
        token = f"BA_{secrets.token_urlsafe(24)}"
        bake.notification_actions[token] = {
            "bake_id": bake.id,
            "step_id": first,
            "generation": run.notification_generation,
            "action": action,
        }
        actions.append(
            {"action": token, "title": label, "authenticationRequired": True}
        )
    definitions = bake.recipe_snapshot.by_id
    if len(step_ids) > 1 or catchup:
        message = f"{len(step_ids)} outstanding: " + "; ".join(
            definitions[step_id].title for step_id in step_ids
        )
        message += f". Buttons apply to {title}. Review the timeline."
    else:
        message = definitions[first].instructions
    if any(
        step_id
        in ("preheat_oven", "oven_ready", "bake_start", "remove_lid", "bake_finish")
        for step_id in step_ids
    ):
        message += " Hot cast iron: use dry oven gloves; avoid burns."
    return {
        "title": "Bread Assistant — " + ("catch-up" if catchup else title),
        "message": message[:900],
        "data": {
            "tag": f"bread_assistant_{bake.id}",
            "url": dashboard_path,
            "actions": actions,
        },
    }
