"""Elapsed time, biological gates, independent anchors and prepared starters."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.bread_assistant.models import BakeStatus, DomainError, StepStatus
from custom_components.bread_assistant.recipe_catalog import load_catalog
from custom_components.bread_assistant.scheduler import (
    adjust,
    complete,
    create_bake,
    lifecycle,
    recompute,
    snooze,
)

START = datetime(2026, 11, 14, 10, tzinfo=UTC)


def bake(**kwargs):
    return create_bake(next(iter(load_catalog().values())), START, **kwargs)


def test_gates_and_lateness():
    b = bake()
    with pytest.raises(DomainError, match="prerequisites"):
        complete(b, "knead_start", START)
    complete(b, "feed_starter", START)
    complete(b, "autolyse_start", START + timedelta(minutes=180))
    recompute(b, START + timedelta(minutes=240))
    assert b.step_runs["starter_ready"].status == StepStatus.READY
    assert b.step_runs["starter_ready"].completed_at is None
    complete(b, "starter_ready", START + timedelta(minutes=240))
    complete(b, "autolyse_complete", START + timedelta(minutes=257))
    assert b.step_runs["knead_start"].due_at == START + timedelta(minutes=257)
    assert b.step_runs["autolyse_start"].planned_at == START + timedelta(minutes=180)
    complete(b, "knead_start", START + timedelta(minutes=257))
    complete(b, "bulk_start", START + timedelta(minutes=262))
    complete(b, "fold_1", START + timedelta(minutes=310))
    assert b.step_runs["fold_2"].due_at == START + timedelta(minutes=322)


def test_skip_feeding_retains_readiness_and_recalculates():
    b = bake(starter_id="my-rye", starter_workflow="prepared")
    assert b.starter_id == "my-rye"
    assert b.step_runs["feed_starter"].status == StepStatus.SKIPPED
    assert "Intentionally" in b.step_runs["feed_starter"].notes
    assert b.step_runs["starter_ready"].completed_at is None
    assert b.step_runs["autolyse_start"].due_at == START
    assert b.step_runs["autolyse_start"].planned_at == START + timedelta(minutes=180)
    complete(b, "autolyse_start", START)
    complete(b, "autolyse_complete", START + timedelta(minutes=60))
    with pytest.raises(DomainError):
        complete(b, "knead_start", START + timedelta(minutes=60))
    complete(b, "starter_ready", START + timedelta(minutes=70))
    assert b.step_runs["knead_start"].due_at == START + timedelta(minutes=70)


def test_explicit_ready_and_no_provider():
    b = bake(starter_workflow="prepared", starter_ready=True)
    assert b.starter_id is None
    assert b.step_runs["starter_ready"].status == StepStatus.DONE
    with pytest.raises(DomainError):
        bake(starter_ready=True)


def test_snooze_adjust_pause_and_idempotence():
    b = bake()
    due = b.step_runs["feed_starter"].due_at
    assert snooze(b, "feed_starter", 10, START)
    assert not snooze(b, "feed_starter", 10, START)
    assert b.step_runs["feed_starter"].due_at == due
    lifecycle(b, "pause_bake", START)
    assert b.status == BakeStatus.PAUSED
    lifecycle(b, "resume_bake", START + timedelta(hours=20))
    assert b.step_runs["feed_starter"].due_at == due
    adjust(b, "feed_starter", START + timedelta(minutes=17), START)
    assert b.step_runs["starter_ready"].due_at == START + timedelta(minutes=257)
    assert b.step_runs["autolyse_start"].due_at == START + timedelta(minutes=180)
    assert complete(b, "feed_starter", START + timedelta(minutes=17))
    assert not complete(b, "feed_starter", START + timedelta(minutes=18))
    assert b.step_runs["feed_starter"].completed_at == START + timedelta(minutes=17)


@pytest.mark.parametrize(
    "start",
    [
        datetime(2026, 11, 14, 18, 35, tzinfo=ZoneInfo("Europe/Warsaw")),
        datetime(2026, 3, 28, 18, 35, tzinfo=ZoneInfo("Europe/Warsaw")),
        datetime(2026, 10, 24, 18, 35, tzinfo=ZoneInfo("Europe/Warsaw")),
    ],
)
def test_midnight_and_dst(start):
    b = create_bake(next(iter(load_catalog().values())), start)
    finish = b.step_runs["bake_finish"].due_at
    assert finish - b.started_at == timedelta(minutes=1320)
    assert finish.tzinfo == UTC
    assert finish.astimezone(start.tzinfo).date() > start.date()


def test_naive_and_fixed_timer_early_rejected():
    with pytest.raises(DomainError, match="timezone"):
        create_bake(next(iter(load_catalog().values())), datetime(2026, 1, 1))
    b = bake(starter_workflow="prepared", starter_ready=True)
    complete(b, "autolyse_start", START)
    with pytest.raises(DomainError, match="deadline"):
        complete(b, "autolyse_complete", START)
