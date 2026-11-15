"""Domain records. No Home Assistant dependencies."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .i18n import Translator


class DomainError(ValueError):
    """An invalid user transition or recipe."""

    def __init__(self, translation_key: str, **placeholders: Any) -> None:
        self.translation_key = translation_key
        self.placeholders = placeholders
        super().__init__(translation_key)

    def __str__(self) -> str:
        return Translator().error(self)


def utc(value: datetime) -> datetime:
    """Reject ambiguous local timestamps; normalize elapsed-time arithmetic to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainError("timestamp_timezone")
    return value.astimezone(UTC)


def parse_time(value: str) -> datetime:
    try:
        return utc(datetime.fromisoformat(value))
    except (TypeError, ValueError) as err:
        raise DomainError("invalid_datetime") from err


class BakeStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELED = "canceled"


class StepStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    SKIPPED = "skipped"


class StepKind(StrEnum):
    ACTION = "action"
    TIMER = "timer"
    CHECKPOINT = "checkpoint"
    MILESTONE = "milestone"


class DependencyKind(StrEnum):
    AFTER_START = "after_start"
    AFTER_COMPLETION = "after_completion"
    PARALLEL_ANCHOR = "parallel_anchor"
    ABSOLUTE = "absolute"


@dataclass(frozen=True, slots=True)
class Dependency:
    kind: DependencyKind
    offset_minutes: int = 0
    anchor: str | None = None
    at: datetime | None = None


@dataclass(frozen=True, slots=True)
class StepDefinition:
    id: str
    title: str
    kind: StepKind
    instructions: str
    offset_minutes: int
    dependencies: tuple[Dependency, ...]
    prerequisites: tuple[str, ...] = ()
    duration_minutes: int = 0
    requires_confirmation: bool = True
    alert_policy: str = "due"
    optional: bool = False
    reference: bool = False
    minimum_minutes: int | None = None


@dataclass(frozen=True, slots=True)
class RecipeDefinition:
    id: str
    version: int
    title: str
    url: str
    ingredients: tuple[str, ...]
    steps: tuple[StepDefinition, ...]

    @property
    def by_id(self) -> dict[str, StepDefinition]:
        return {step.id: step for step in self.steps}


@dataclass(slots=True)
class StepRun:
    step_id: str
    status: StepStatus
    planned_at: datetime
    due_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    snoozed_until: datetime | None = None
    acknowledged_at: datetime | None = None
    adjusted_at: datetime | None = None
    notification_generation: int = 0
    last_notified_at: datetime | None = None
    notes: str = ""

    @property
    def finished(self) -> bool:
        return self.status in (StepStatus.DONE, StepStatus.SKIPPED)


@dataclass(slots=True)
class LiveActivity:
    """Reserved push activity identity; no device tokens are stored here."""

    bake_id: str
    target: str
    started_at: datetime


@dataclass(slots=True)
class BakeRun:
    id: str
    recipe_snapshot: RecipeDefinition
    started_at: datetime
    status: BakeStatus
    step_runs: dict[str, StepRun]
    starter_id: str | None = None
    starter_workflow: str = "feed"
    pause_started_at: datetime | None = None
    archived_at: datetime | None = None
    notes: str = ""
    revision: int = 0
    # Persisted random tokens survive restart. Values bind bake/step/generation.
    notification_actions: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def recipe_id(self) -> str:
        return self.recipe_snapshot.id

    @property
    def recipe_version(self) -> int:
        return self.recipe_snapshot.version
