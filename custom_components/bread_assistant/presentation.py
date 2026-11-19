"""Describe ongoing processes from confirmed events, without changing the bake."""

from .i18n import Translator
from .models import BakeRun, BakeStatus, StepStatus

PROCESS_STEPS = (
    ("starter", "feed_starter", "starter_ready"),
    ("autolyse", "autolyse_start", "autolyse_complete"),
    ("kneading", "knead_start", "bulk_start"),
    ("bulk", "bulk_start", "bulk_ready"),
    ("bench_rest", "preshape", "final_shape"),
    ("cold_proof", "cold_proof_start", "dough_ready"),
    ("preheating", "preheat_oven", "oven_ready"),
    ("covered_bake", "bake_start", "remove_lid"),
    ("uncovered_bake", "remove_lid", "bake_finish"),
    ("cooling", "bake_finish", "cooling_check"),
)


def ongoing_processes(bake: BakeRun | None, tr: Translator) -> list[dict[str, str]]:
    """Elapsed time never ends a process or asserts readiness; human events do."""
    if bake is None or bake.status not in (BakeStatus.ACTIVE, BakeStatus.PAUSED):
        return []
    processes = []
    for process_id, start_id, end_id in PROCESS_STEPS:
        start = bake.step_runs.get(start_id)
        end = bake.step_runs.get(end_id)
        if (
            start is None
            or start.status != StepStatus.DONE
            or start.completed_at is None
            or end is None
            or end.finished
        ):
            continue
        fields = {
            field: tr.recipe(bake.recipe_snapshot, f"processes.{process_id}.{field}")
            for field in ("title", "hint", "started_label")
        }
        if fields["title"]:
            processes.append(
                {
                    "id": process_id,
                    "started_at": start.completed_at.isoformat(),
                    **fields,
                }
            )
    return processes
