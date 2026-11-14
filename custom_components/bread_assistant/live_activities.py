"""Companion Live Activities: discrete updates, durable identity, bounded retries.

API: https://companion.home-assistant.io/docs/notifications/live-activities/
Only documented Live Activity fields are sent; actionable reminders are separate.
"""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import scheduler
from .models import BakeRun, BakeStatus, DomainError, LiveActivity
from .notifications import is_mobile_app_target
from .storage import BakeStorage

RENEW_AFTER = timedelta(hours=7, minutes=55)
RETRY_AFTER = timedelta(minutes=15)


def activity_tag(bake_id: str) -> str:
    """Separate from reminders; UUID tags fit Companion's 64-character limit."""
    return f"bread_assistant_live_{bake_id}"


def activity_payload(
    bake: BakeRun, now: datetime, dashboard_path: str
) -> dict[str, Any]:
    """Use the same required-step progress and actionable order as the sensors."""
    steps = scheduler.actionable(bake, include_paused=True)
    current = steps[0] if steps else None
    title = bake.recipe_snapshot.by_id[current.step_id].title if current else "Bake"
    paused = bake.status == BakeStatus.PAUSED
    due = current is not None and current.due_at <= now
    status = (
        "Paused (process time continues)"
        if paused
        else ("Action due — confirm manually" if due else "Next action")
    )
    required = [
        bake.step_runs[step.id]
        for step in bake.recipe_snapshot.steps
        if not step.optional
    ]
    data: dict[str, Any] = {
        "tag": activity_tag(bake.id),
        "live_update": True,
        "critical_text": f"Paused · {title}" if paused else title,
        "progress": sum(run.finished for run in required),
        "progress_max": len(required),
        "chronometer": bool(current and not paused and not due),
        "notification_icon": "mdi:bread-slice",
        "silent": True,
        "url": dashboard_path,
    }
    if data["chronometer"] and current:
        # An absolute timestamp stays stable across reminder ticks/restarts.
        data["when"] = int(current.due_at.timestamp())
        data["when_relative"] = False
    return {
        "title": "Bread Assistant",
        "message": f"{title} · {status}",
        "data": data,
    }


class LiveActivities:
    """Called under the coordinator lock, after durable domain changes."""

    def __init__(
        self,
        hass: HomeAssistant,
        storage: BakeStorage,
        options: dict[str, Any],
        closed: Callable[[], bool],
    ) -> None:
        self.hass = hass
        self.storage = storage
        self.options = options
        self.closed = closed
        self.error: str | None = None
        self.retry_at: datetime | None = None
        self._last_delivery: tuple[str, dict[str, Any]] | None = None

    def next_deadline(self) -> datetime | None:
        if self.retry_at:
            return self.retry_at
        if not self.options["live_activities_enabled"]:
            return None
        deadlines = [r.started_at + RENEW_AFTER for r in self.storage.live_activities]
        return min(deadlines) if deadlines else None

    async def _send(self, target: str, payload: dict[str, Any]) -> None:
        if not is_mobile_app_target(target):
            raise DomainError("Only mobile_app notification targets are supported")
        domain, service = target.split(".", 1)
        if not self.hass.services.has_service(domain, service):
            raise DomainError("Live Activity notification destination is unavailable")
        async with asyncio.timeout(15):
            await self.hass.services.async_call(domain, service, payload, blocking=True)

    async def async_sync(
        self,
        bake: BakeRun | None,
        archives: list[dict[str, Any]],
        now: datetime,
        *,
        force: bool = False,
    ) -> None:
        """Reconcile persisted activities with the latest bake and configuration.

        Reserve identity before starting. Clear before forgetting it. Both can
        safely be replayed following a crash. Keep old-bake cleanup independently
        of the latest snapshot so a failed end cannot be lost on the next start.
        """
        if self.closed():
            return
        if self.retry_at and now < self.retry_at and not force:
            return
        target = (
            self.options["live_activity_notify_target"]
            if self.options["live_activities_enabled"]
            and bake
            and bake.status in (BakeStatus.ACTIVE, BakeStatus.PAUSED)
            else ""
        )
        self.retry_at = None
        cleanup_error: str | None = None
        try:
            for record in list(self.storage.live_activities):
                if self.closed():
                    return
                if (
                    not bake
                    or record.bake_id != bake.id
                    or record.target != target
                    or now >= record.started_at + RENEW_AFTER
                    or now < record.started_at  # clock correction/backup restore
                ):
                    try:
                        await self._send(
                            record.target,
                            {
                                "message": "clear_notification",
                                "data": {"tag": activity_tag(record.bake_id)},
                            },
                        )
                        await self.storage.async_save(
                            bake,
                            archives,
                            live_activities=[
                                r for r in self.storage.live_activities if r != record
                            ],
                        )
                        if (
                            self._last_delivery
                            and self._last_delivery[0] == record.target
                            and self._last_delivery[1]["data"]["tag"]
                            == activity_tag(record.bake_id)
                        ):
                            self._last_delivery = None
                    except (
                        ValueError,
                        TimeoutError,
                        HomeAssistantError,
                        OSError,
                    ) as err:
                        # A removed old phone must not block a new destination.
                        cleanup_error = f"Live Activity cleanup failed: {err}"
            if self.closed():
                return
            if not target or not bake:
                self.error = cleanup_error
                if cleanup_error:
                    self.retry_at = now + RETRY_AFTER
                return
            # Check before reserving a start for an invalid/unavailable service.
            if not is_mobile_app_target(target):
                raise DomainError("Only mobile_app notification targets are supported")
            if not self.hass.services.has_service(*target.split(".", 1)):
                raise DomainError(
                    "Live Activity notification destination is unavailable"
                )
            active_record = next(
                (
                    r
                    for r in self.storage.live_activities
                    if r.bake_id == bake.id and r.target == target
                ),
                None,
            )
            if active_record and (
                now >= active_record.started_at + RENEW_AFTER
                or now < active_record.started_at
            ):
                # The clear failed: retry later instead of updating an expired
                # activity or issuing a duplicate push-to-start on the same tag.
                self.error = cleanup_error
                self.retry_at = now + RETRY_AFTER
                return
            if active_record is None:
                await self.storage.async_save(
                    bake,
                    archives,
                    live_activities=[
                        *self.storage.live_activities,
                        LiveActivity(bake.id, target, now),
                    ],
                )
                self._last_delivery = None
            if self.closed():
                return
            payload = activity_payload(bake, now, self.options["dashboard_path"])
            delivery = (target, payload)
            if force or delivery != self._last_delivery:
                await self._send(target, payload)
                self._last_delivery = delivery
            self.error = cleanup_error
            if cleanup_error:
                self.retry_at = now + RETRY_AFTER
        except (ValueError, TimeoutError, HomeAssistantError, OSError) as err:
            # Notification or metadata-write failures must not undo a bake action.
            self.error = f"Live Activity delivery failed: {err}"
            self.retry_at = now + RETRY_AFTER
