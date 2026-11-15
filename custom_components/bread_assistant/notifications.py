"""Companion payloads and opaque, persisted action capabilities."""

import re
import secrets
from typing import Any

from .i18n import Translator
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
    translator: Translator | None = None,
) -> dict[str, Any]:
    """Buttons target the first listed step; a summary never completes a group."""
    tr = translator or Translator()
    first = step_ids[0]
    run = bake.step_runs[first]
    bake.notification_actions = {
        token: value
        for token, value in bake.notification_actions.items()
        if value["step_id"] not in step_ids
    }
    actions = []
    title = tr.step(bake.recipe_snapshot, first, "title")
    for action, label in (
        ("done", tr.text("content.notifications.done", title=title)),
        ("snooze", tr.text("content.notifications.snooze")),
    ):
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
    if len(step_ids) > 1 or catchup:
        message = tr.text(
            "content.notifications.outstanding",
            count=len(step_ids),
            title=title,
            steps="; ".join(
                tr.step(bake.recipe_snapshot, step_id, "title") for step_id in step_ids
            ),
        )
    else:
        message = tr.step(bake.recipe_snapshot, first, "instructions")
    hot_warning = ""
    if any(
        step_id
        in ("preheat_oven", "oven_ready", "bake_start", "remove_lid", "bake_finish")
        for step_id in step_ids
    ):
        hot_warning = " " + tr.text("content.notifications.hot")
    message = message[: 900 - len(hot_warning)] + hot_warning
    return {
        "title": tr.text(
            "content.notifications.title",
            title=tr.text("content.notifications.catchup") if catchup else title,
        ),
        "message": message,
        "data": {
            "tag": f"bread_assistant_{bake.id}",
            "url": dashboard_path,
            "actions": actions,
        },
    }
