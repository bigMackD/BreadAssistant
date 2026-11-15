"""Serialize changes, persist before publication, and own a single UTC callback."""

import asyncio
import logging
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_CORE_CONFIG_UPDATE,
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from . import scheduler
from .const import DEFAULT_OPTIONS, DEFAULT_RECIPE, DOMAIN
from .i18n import Translator, load_translations, resolve_language
from .live_activities import LiveActivities
from .models import BakeRun, BakeStatus, DomainError, StepRun, parse_time, utc
from .notifications import prepare_notification
from .recipe_catalog import load_catalog
from .storage import BakeStorage

_LOGGER = logging.getLogger(__name__)


class BakeCoordinator:
    """A push coordinator with transactional in-memory mutations and no polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        clock: Callable[[], datetime] = dt_util.utcnow,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.clock = clock
        self.options = DEFAULT_OPTIONS | entry.data | entry.options
        self.storage = BakeStorage(hass)
        self.bake: BakeRun | None = None
        self.archives: list[dict[str, Any]] = []
        self.catalog: dict[str, Any] = {}
        self._last_error: tuple[str, Exception] | None = None
        self.last_sync: datetime | None = None
        self._lock = asyncio.Lock()
        self._listeners: set[Callable[[], None]] = set()
        self._unsubscribers: list[Callable[[], None]] = []
        self._cancel_timer: Callable[[], None] | None = None
        self._timer_generation = 0
        self.closed = False
        self.live_activities = LiveActivities(
            hass, self.storage, self.options, lambda: self.closed
        )

    @property
    def translator(self) -> Translator:
        return Translator(
            resolve_language(self.options["language"], self.hass.config.language)
        )

    @property
    def last_error(self) -> str | None:
        if self._last_error is None:
            return None
        kind, error = self._last_error
        return self.translator.text(
            f"content.diagnostics.{kind}", error=self.translator.error(error)
        )

    async def async_load(self) -> None:
        await self.hass.async_add_executor_job(load_translations)
        self.catalog = await self.hass.async_add_executor_job(load_catalog)
        try:
            self.bake, self.archives = await self.storage.async_load()
            if self.bake:
                scheduler.recompute(self.bake, self.clock())
        except (ValueError, KeyError, TypeError) as err:
            raise ConfigEntryError(
                self.translator.text(
                    "exceptions.restore.message", error=self.translator.error(err)
                ),
                translation_domain=DOMAIN,
                translation_key="restore",
                translation_placeholders={"error": self.translator.error(err)},
            ) from err

    async def async_start(self) -> None:
        self._unsubscribers.append(
            self.hass.bus.async_listen(
                EVENT_CORE_CONFIG_UPDATE, self._async_language_updated
            )
        )
        self._unsubscribers.append(
            self.hass.bus.async_listen(
                "service_registered", self._async_notify_available
            )
        )
        self._unsubscribers.append(
            self.hass.bus.async_listen(
                "mobile_app_notification_action", self._async_mobile_action
            )
        )
        self._unsubscribers.append(
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, self._async_stop_event
            )
        )
        if self.hass.is_running:
            await self._async_recover()
        else:
            self._unsubscribers.append(
                self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STARTED, self._async_started
                )
            )

    async def _async_language_updated(self, event: Event) -> None:
        if self.options["language"] != "auto":
            return
        async with self._lock:
            await self._async_sync_live_activity(force=True)
            self._publish("language_changed")

    async def _async_started(self, event: Event) -> None:
        await self._async_recover()

    async def _async_notify_available(self, event: Event) -> None:
        target = f"{event.data.get('domain')}.{event.data.get('service')}"
        targets = {r.target for r in self.storage.live_activities}
        if self.options["live_activities_enabled"]:
            targets.add(self.options["live_activity_notify_target"])
        if target not in targets:
            return
        async with self._lock:
            await self._async_sync_live_activity(force=True)
            self._schedule()

    async def _async_recover(self) -> None:
        try:
            await self.async_tick(catchup=True)
        except (HomeAssistantError, OSError) as err:
            self._last_error = ("storage", err)
            _LOGGER.error("%s; retrying in one minute", self.last_error)
            self._publish("storage_error")
            self._schedule(not_before=utc(self.clock()) + timedelta(minutes=1))

    async def _async_stop_event(self, event: Event) -> None:
        await self.async_shutdown()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def _publish(self, cause: str) -> None:
        if self.closed:
            return
        self.last_sync = self.clock()
        for listener in tuple(self._listeners):
            listener()
        self.hass.bus.async_fire(
            f"{DOMAIN}_updated",
            {
                "bake_id": self.bake.id if self.bake else None,
                "revision": self.bake.revision if self.bake else 0,
                "cause": cause,
            },
        )
        _LOGGER.debug("Recomputed bake schedule: %s", cause)

    async def _commit(self, bake: BakeRun, cause: str) -> None:
        archives = list(self.archives)
        if bake.status in (BakeStatus.COMPLETED, BakeStatus.CANCELED):
            if not any(a["id"] == bake.id for a in archives):
                archives.append(
                    {
                        "id": bake.id,
                        "recipe_id": bake.recipe_id,
                        "recipe_version": bake.recipe_version,
                        "status": bake.status,
                        "started_at": bake.started_at.isoformat(),
                        "archived_at": bake.archived_at.isoformat()
                        if bake.archived_at
                        else None,
                        "starter_id": bake.starter_id,
                        "done_count": sum(r.finished for r in bake.step_runs.values()),
                    }
                )
        await self.storage.async_save(bake, archives)
        self.bake, self.archives = bake, archives[-50:]
        if self._last_error and self._last_error[0] == "storage":
            self._last_error = None
        self._publish(cause)
        if cause not in ("deadline", "catchup"):
            self.live_activities.retry_at = None
            await self._async_sync_live_activity(force=cause == "adjust_step")

    async def _async_sync_live_activity(self, *, force: bool = False) -> None:
        previous_error = self.live_activities.error
        await self.live_activities.async_sync(
            self.bake, self.archives, utc(self.clock()), force=force
        )
        if self.live_activities.error != previous_error:
            if self.live_activities.error:
                _LOGGER.warning(
                    "%s; retrying in 15 minutes", self.live_activities.error
                )
            self._publish("live_activity_delivery")

    async def async_action(self, action: str, data: dict[str, Any]) -> None:
        async with self._lock:
            if self.closed:
                raise DomainError("unloading")
            now = utc(self.clock())
            if action == "start_bake":
                if self.bake and self.bake.status in (
                    BakeStatus.ACTIVE,
                    BakeStatus.PAUSED,
                ):
                    raise DomainError("active_bake")
                recipe_id = data.get("recipe_id", DEFAULT_RECIPE)
                if recipe_id not in self.catalog:
                    raise DomainError("unknown_recipe")
                bake = scheduler.create_bake(
                    self.catalog[recipe_id],
                    parse_time(data["start_time"]) if "start_time" in data else now,
                    starter_id=data.get("starter_id"),
                    starter_workflow=data.get("starter_workflow", "feed"),
                    starter_ready=data.get("starter_ready", False),
                )
            else:
                if self.bake is None or data.get("bake_id") != self.bake.id:
                    raise DomainError("stale_bake")
                bake = deepcopy(self.bake)
                step_id = data.get("step_id", "")
                if action in ("complete_step", "snooze_step", "adjust_step"):
                    if step_id not in bake.step_runs:
                        raise DomainError("unknown_step_id")
                    if action == "complete_step":
                        # A repeated completion after finalization is also harmless.
                        if bake.step_runs[step_id].finished:
                            return
                        if not scheduler.complete(bake, step_id, now):
                            return
                    elif action == "snooze_step":
                        if not scheduler.snooze(bake, step_id, data["minutes"], now):
                            return
                    else:
                        scheduler.adjust(bake, step_id, parse_time(data["due_at"]), now)
                elif not scheduler.lifecycle(bake, action, now):
                    return
            await self._commit(bake, action)
            self._schedule()
        # A due transition is delivered immediately without waiting for a polling tick.
        await self.async_tick(catchup=action == "resume_bake")

    def current_steps(self) -> list[StepRun]:
        return scheduler.actionable(self.bake, include_paused=True) if self.bake else []

    def _reminder_at(self, run: StepRun) -> datetime:
        due = max(run.due_at, run.snoozed_until or run.due_at)
        if run.last_notified_at is not None:
            due = max(
                due,
                run.last_notified_at
                + timedelta(minutes=self.options["reminder_minutes"]),
            )
        return due

    def _schedule(self, *, not_before: datetime | None = None) -> None:
        self._timer_generation += 1
        generation = self._timer_generation
        if self._cancel_timer:
            self._cancel_timer()
            self._cancel_timer = None
        if self.closed:
            return
        now = self.clock()
        deadlines: list[datetime] = []
        live_deadline = self.live_activities.next_deadline()
        if live_deadline:
            deadlines.append(max(live_deadline, now + timedelta(seconds=1)))
        steps = (
            self.current_steps()
            if self.bake and self.bake.status == BakeStatus.ACTIVE
            else []
        )
        for run in steps:
            if run.due_at > now:
                deadlines.append(run.due_at)
            if self.bake.recipe_snapshot.by_id[run.step_id].alert_policy != "silent":
                deadlines.append(
                    max(self._reminder_at(run), now + timedelta(seconds=1))
                )
        if not deadlines:
            return

        async def timer(at: datetime) -> None:
            if self.closed or generation != self._timer_generation:
                return
            try:
                await self.async_tick()
            except (HomeAssistantError, OSError) as err:
                self._last_error = ("storage", err)
                _LOGGER.error("%s; retrying in one minute", self.last_error)
                self._publish("storage_error")
                if not self.closed and generation == self._timer_generation:
                    self._cancel_timer = async_track_point_in_utc_time(
                        self.hass, timer, utc(self.clock()) + timedelta(minutes=1)
                    )

        self._cancel_timer = async_track_point_in_utc_time(
            self.hass, timer, max(min(deadlines), not_before or min(deadlines))
        )

    async def async_tick(self, *, catchup: bool = False) -> None:
        async with self._lock:
            if self.closed:
                return
            if not self.bake or self.bake.status != BakeStatus.ACTIVE:
                await self._async_sync_live_activity()
                self._schedule()
                return
            now = utc(self.clock())
            bake = deepcopy(self.bake)
            scheduler.recompute(bake, now)
            due = [
                r
                for r in scheduler.actionable(bake)
                if bake.recipe_snapshot.by_id[r.step_id].alert_policy == "due"
                and self._reminder_at(r) <= now
            ]
            # Reserve delivery durably before side effects. On restart we never
            # replay all pending timers, and a repeated callback cannot double-send.
            for run in due:
                run.last_notified_at = now
                run.notification_generation += 1
            scheduler.recompute(bake, now)
            payload = (
                prepare_notification(
                    bake,
                    [r.step_id for r in due],
                    catchup,
                    self.options["dashboard_path"],
                    self.translator,
                )
                if due and self.options["notifications_enabled"]
                else None
            )
            if due or bake != self.bake:
                await self._commit(bake, "catchup" if catchup else "deadline")
            if due and not self.closed:
                await self._async_notify([r.step_id for r in due], catchup, payload)
            await self._async_sync_live_activity()
            self._schedule()

    async def _async_notify(
        self, step_ids: list[str], catchup: bool, payload: dict[str, Any] | None = None
    ) -> None:
        self.hass.bus.async_fire(
            f"{DOMAIN}_reminder",
            {
                "bake_id": self.bake.id if self.bake else None,
                "step_ids": step_ids,
                "catchup": catchup,
            },
        )

        target = self.options["notify_target"]
        if payload is None or not target:
            return
        try:
            if not target.startswith("notify.mobile_app_"):
                raise DomainError("mobile_only")
            domain, service = target.split(".", 1)
            if not self.hass.services.has_service(domain, service):
                raise DomainError("mobile_unavailable")
            async with asyncio.timeout(15):
                await self.hass.services.async_call(
                    domain, service, payload, blocking=True
                )
            self._last_error = None
        except (ValueError, TimeoutError, HomeAssistantError) as err:
            self._last_error = ("reminder", err)
            _LOGGER.warning("%s; retrying at reminder interval", self.last_error)
        self._publish("notification_delivery")

    async def _async_mobile_action(self, event: Event) -> None:
        token = event.data.get("action")
        if not isinstance(token, str):
            return
        async with self._lock:
            bake = self.bake
            if self.closed or not bake or bake.status != BakeStatus.ACTIVE:
                return
            action = bake.notification_actions.get(token)
            if action is None:
                _LOGGER.debug("Ignoring unknown or stale notification capability")
                return
            run = bake.step_runs[action["step_id"]]
            if (
                action["bake_id"] != bake.id
                or run.finished
                or action["generation"] != run.notification_generation
                or not scheduler.eligible(bake, bake.recipe_snapshot.by_id[run.step_id])
            ):
                return
            candidate = deepcopy(bake)
            try:
                if action["action"] == "done":
                    scheduler.complete(candidate, run.step_id, self.clock())
                else:
                    scheduler.snooze(candidate, run.step_id, 10, self.clock())
            except DomainError:
                _LOGGER.debug("Notification action no longer applies")
                return
            await self._commit(candidate, "notification_action")
            self._schedule()
        await self.async_tick()

    async def async_shutdown(self) -> None:
        # Invalidate queued callbacks before waiting for any ongoing write/delivery.
        self.closed = True
        self._timer_generation += 1
        if self._cancel_timer:
            self._cancel_timer()
            self._cancel_timer = None
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        async with self._lock:
            self._listeners.clear()
