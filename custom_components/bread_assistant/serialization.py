"""Versioned JSON records shared by Store and pure round-trip tests."""

from dataclasses import asdict
from datetime import datetime
from typing import Any
from uuid import UUID

from .models import (
    BakeRun,
    BakeStatus,
    DomainError,
    LiveActivity,
    StepRun,
    StepStatus,
    parse_time,
    utc,
)
from .notifications import is_mobile_app_target
from .recipe_catalog import recipe_from_dict

SCHEMA_VERSION = 2


def live_activities_from_dict(data: Any) -> list[LiveActivity]:
    """Additive v2 metadata also retains cleanup work for previous bakes."""
    if not isinstance(data, list):
        raise DomainError("live_records")
    records = []
    try:
        for item in data:
            UUID(item["bake_id"])
            if not is_mobile_app_target(item["target"]):
                raise DomainError("live_destination")
            records.append(
                LiveActivity(
                    bake_id=item["bake_id"],
                    target=item["target"],
                    started_at=parse_time(item["started_at"]),
                )
            )
    except (KeyError, TypeError, ValueError, AttributeError) as err:
        raise DomainError("invalid_live_records", error=err) from err
    return records


def live_activities_to_dict(records: list[LiveActivity]) -> list[dict[str, Any]]:
    return [dict(_encode(asdict(record))) for record in records]


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return utc(value).isoformat()
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def bake_to_dict(bake: BakeRun) -> dict[str, Any]:
    return dict(_encode(asdict(bake)))


def bake_from_dict(data: dict[str, Any]) -> BakeRun:
    try:
        recipe = recipe_from_dict(data["recipe_snapshot"])
        runs: dict[str, StepRun] = {}
        for step_id, stored in data["step_runs"].items():
            values = dict(stored)
            for key in (
                "planned_at",
                "due_at",
                "started_at",
                "completed_at",
                "snoozed_until",
                "acknowledged_at",
                "adjusted_at",
                "last_notified_at",
            ):
                values[key] = parse_time(values[key]) if values.get(key) else None
            if values["planned_at"] is None or values["due_at"] is None:
                raise DomainError("missing_times")
            values["status"] = StepStatus(values["status"])
            if values["step_id"] != step_id:
                raise DomainError("step_identity")
            runs[step_id] = StepRun(**values)
            if (
                type(runs[step_id].notification_generation) is not int
                or runs[step_id].notification_generation < 0
            ):
                raise DomainError("generation")
            if runs[step_id].finished and runs[step_id].completed_at is None:
                raise DomainError("actual_time")
        if set(runs) != set(recipe.by_id):
            raise DomainError("stored_steps")
        bake = BakeRun(
            id=data["id"],
            recipe_snapshot=recipe,
            started_at=parse_time(data["started_at"]),
            status=BakeStatus(data["status"]),
            step_runs=runs,
            starter_id=data.get("starter_id"),
            starter_workflow=data.get("starter_workflow", "feed"),
            pause_started_at=parse_time(data["pause_started_at"])
            if data.get("pause_started_at")
            else None,
            archived_at=parse_time(data["archived_at"])
            if data.get("archived_at")
            else None,
            notes=data.get("notes", ""),
            revision=data.get("revision", 0),
            notification_actions=data.get("notification_actions", {}),
        )
        if bake.starter_workflow not in ("feed", "prepared"):
            raise DomainError("stored_workflow")
        UUID(bake.id)
        if type(bake.revision) is not int or bake.revision < 0:
            raise DomainError("revision")
        if bake.starter_id is not None and (
            not isinstance(bake.starter_id, str)
            or not bake.starter_id.strip()
            or len(bake.starter_id) > 128
        ):
            raise DomainError("starter_reference")
        for action in bake.notification_actions.values():
            if (
                action["step_id"] not in runs
                or action["bake_id"] != bake.id
                or type(action["generation"]) is not int
                or action["action"] not in ("done", "snooze")
            ):
                raise DomainError("stored_action")
        return bake
    except (ValueError, KeyError, TypeError, AttributeError) as err:
        raise DomainError("invalid_stored_bake", error=err) from err


def migrate_payload(data: dict[str, Any], version: int) -> dict[str, Any]:
    """V1 bake snapshots remain valid; starter fields are additive defaults."""
    if version not in (1, SCHEMA_VERSION):
        raise DomainError("storage_version", version=version)
    if not isinstance(data, dict):
        raise DomainError("storage_object")
    result = dict(data)
    result["schema_version"] = SCHEMA_VERSION
    if result.get("bake"):
        result["bake"] = {
            "starter_id": None,
            "starter_workflow": "feed",
            **result["bake"],
        }
    return result
