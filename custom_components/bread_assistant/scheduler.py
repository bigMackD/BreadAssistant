"""Deterministic UTC schedule and explicit human transitions. No IO or HA."""

from datetime import datetime, timedelta
from uuid import uuid4

from .models import (
    BakeRun,
    BakeStatus,
    DependencyKind,
    DomainError,
    RecipeDefinition,
    StepDefinition,
    StepRun,
    StepStatus,
    utc,
)
from .recipe_catalog import topological_steps, validate_recipe


def create_bake(
    recipe: RecipeDefinition,
    started_at: datetime,
    *,
    starter_id: str | None = None,
    starter_workflow: str = "feed",
    starter_ready: bool = False,
) -> BakeRun:
    validate_recipe(recipe)
    started_at = utc(started_at)
    if starter_workflow not in ("feed", "prepared"):
        raise DomainError("workflow")
    if starter_ready and starter_workflow != "prepared":
        raise DomainError("prepared_only")
    if starter_id is not None and (not starter_id.strip() or len(starter_id) > 128):
        raise DomainError("starter_id")
    bake = BakeRun(
        id=str(uuid4()),
        recipe_snapshot=recipe,
        started_at=started_at,
        status=BakeStatus.ACTIVE,
        starter_id=starter_id,
        starter_workflow=starter_workflow,
        step_runs={
            s.id: StepRun(
                step_id=s.id,
                status=StepStatus.PENDING,
                planned_at=started_at + timedelta(minutes=s.offset_minutes),
                due_at=started_at + timedelta(minutes=s.offset_minutes),
            )
            for s in recipe.steps
        },
    )
    if starter_workflow == "prepared":
        feed = bake.step_runs["feed_starter"]
        feed.status = StepStatus.SKIPPED
        feed.completed_at = started_at
        feed.notes = "Intentionally skipped: using an already prepared starter"
        if starter_ready:
            ready = bake.step_runs["starter_ready"]
            ready.status = StepStatus.DONE
            ready.completed_at = ready.acknowledged_at = started_at
            ready.notes = "Starter readiness explicitly confirmed when starting bake"
    recompute(bake, started_at)
    return bake


def eligible(bake: BakeRun, step: StepDefinition) -> bool:
    gates = set(step.prerequisites)
    gates.update(
        dep.anchor
        for dep in step.dependencies
        if dep.kind == DependencyKind.AFTER_COMPLETION and dep.anchor is not None
    )
    return all(bake.step_runs[p].finished for p in gates)


def recompute(bake: BakeRun, now: datetime) -> None:
    """Keep original plans; predict from actual completions when known."""
    now = utc(now)
    for step in topological_steps(bake.recipe_snapshot):
        run = bake.step_runs[step.id]
        if run.finished:
            continue
        anchors: list[datetime] = []
        for dep in step.dependencies:
            if dep.kind == DependencyKind.AFTER_START:
                # Prepared workflow uses the same autolyse, starting immediately.
                offset = (
                    0
                    if (
                        bake.starter_workflow == "prepared"
                        and step.id == "autolyse_start"
                    )
                    else dep.offset_minutes
                )
                anchor = bake.started_at
            elif dep.kind == DependencyKind.ABSOLUTE:
                assert dep.at is not None
                anchor, offset = utc(dep.at), dep.offset_minutes
            else:
                assert dep.anchor is not None
                previous = bake.step_runs[dep.anchor]
                anchor = previous.completed_at or previous.due_at
                offset = dep.offset_minutes
                if bake.starter_workflow == "prepared" and step.id == "starter_ready":
                    offset = 0
            anchors.append(anchor + timedelta(minutes=offset))
        # Completed gates constrain the start, even if not a timed anchor.
        for prerequisite in step.prerequisites:
            completed_at = bake.step_runs[prerequisite].completed_at
            if completed_at is not None:
                anchors.append(completed_at)
        new_due = max(anchors)
        if run.adjusted_at is not None:
            new_due = max(new_due, run.adjusted_at)
        if new_due != run.due_at:
            run.notification_generation += 1
            run.last_notified_at = None
        run.due_at = new_due
        run.status = (
            StepStatus.READY
            if eligible(bake, step) and new_due <= now
            else StepStatus.PENDING
        )
    # Prune obsolete capabilities on every transition; bound persisted tokens.
    bake.notification_actions = {
        token: action
        for token, action in bake.notification_actions.items()
        if action["step_id"] in bake.step_runs
        and not bake.step_runs[action["step_id"]].finished
        and action["generation"]
        == bake.step_runs[action["step_id"]].notification_generation
        and bake.status == BakeStatus.ACTIVE
    }


def require_active(bake: BakeRun) -> None:
    if bake.status != BakeStatus.ACTIVE:
        raise DomainError("active_required")


def complete(bake: BakeRun, step_id: str, now: datetime) -> bool:
    require_active(bake)
    now = utc(now)
    if now < bake.started_at:
        raise DomainError("not_started")
    if step_id not in bake.step_runs:
        raise DomainError("unknown_step")
    run = bake.step_runs[step_id]
    if run.finished:
        return False
    step = bake.recipe_snapshot.by_id[step_id]
    if not eligible(bake, step):
        raise DomainError("prerequisites")
    # Deadlines are reminders; the person confirms actual completion, even early.
    run.status = StepStatus.DONE
    run.started_at = run.completed_at = run.acknowledged_at = now
    run.snoozed_until = None
    run.notification_generation += 1
    bake.revision += 1
    recompute(bake, now)
    if all(
        r.finished
        for s in bake.recipe_snapshot.steps
        if not s.optional
        for r in [bake.step_runs[s.id]]
    ):
        bake.status = BakeStatus.COMPLETED
        bake.archived_at = now
        bake.notification_actions.clear()
    return True


def snooze(bake: BakeRun, step_id: str, minutes: int, now: datetime) -> bool:
    require_active(bake)
    if not 1 <= minutes <= 1440:
        raise DomainError("snooze_range")
    run = bake.step_runs[step_id]
    if run.finished:
        return False
    until = utc(now) + timedelta(minutes=minutes)
    # Repeated request at the same instant is a no-op.
    if run.snoozed_until == until:
        return False
    run.snoozed_until = until
    run.last_notified_at = None
    run.notification_generation += 1
    bake.revision += 1
    recompute(bake, now)
    return True


def adjust(bake: BakeRun, step_id: str, due_at: datetime, now: datetime) -> None:
    require_active(bake)
    run = bake.step_runs[step_id]
    if run.finished:
        raise DomainError("finished_step")
    run.adjusted_at = utc(due_at)
    run.snoozed_until = None
    run.notification_generation += 1
    run.last_notified_at = None
    bake.revision += 1
    recompute(bake, now)


def lifecycle(bake: BakeRun, action: str, now: datetime) -> bool:
    now = utc(now)
    target = {
        "pause_bake": BakeStatus.PAUSED,
        "resume_bake": BakeStatus.ACTIVE,
        "cancel_bake": BakeStatus.CANCELED,
    }[action]
    if bake.status == target:
        return False
    if bake.status not in (BakeStatus.ACTIVE, BakeStatus.PAUSED):
        raise DomainError("finished_bake")
    bake.status = target
    bake.pause_started_at = now if target == BakeStatus.PAUSED else None
    bake.revision += 1
    bake.notification_actions.clear()
    for run in bake.step_runs.values():
        run.notification_generation += 1
    if target == BakeStatus.CANCELED:
        bake.archived_at = now
    recompute(bake, now)
    return True


def actionable(bake: BakeRun, *, include_paused: bool = False) -> list[StepRun]:
    """Unfinished gated steps, including future estimates, in deadline order."""
    if bake.status != BakeStatus.ACTIVE and not (
        include_paused and bake.status == BakeStatus.PAUSED
    ):
        return []
    return sorted(
        (
            bake.step_runs[s.id]
            for s in bake.recipe_snapshot.steps
            if not bake.step_runs[s.id].finished and eligible(bake, s)
        ),
        key=lambda r: (r.due_at, bake.recipe_snapshot.by_id[r.step_id].offset_minutes),
    )
