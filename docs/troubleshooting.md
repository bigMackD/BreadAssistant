# Troubleshooting

## Setup or upgrade fails

Check the HA version, complete directory copy and logs. Schema/recipe errors fail
setup without replacing the saved bake. Unknown Store versions indicate a newer
integration wrote the file; restore the matching integration version or a consistent
backup. HA may preserve malformed JSON as a `.corrupt.*` file; retain that copy
before recovery. Do not delete all of `.storage` and do not edit storage while HA
is running. The latest full bake plus up to 50 archive summaries are retained.

## No push notifications

Open integration Configure, enable notifications and select an available
`notify.mobile_app_*` action. An empty destination is supported and sends no push.
Verify the selected action in Developer Tools → Actions, check iOS permission and
the app's HA server registration. Missing/failed destinations never stop a bake:
inspect `sensor.bread_assistant_status` → `last_error`, the dashboard and HA logs.
Retries use the selected reminder interval; Snooze overrides the next reminder.
When multiple steps are outstanding, one summary replaces the current bake notice;
Done/Snooze apply only to the first named step. Silent technique substeps remain
visible on the dashboard but do not independently send push.

The integration emits `bread_assistant_reminder` (bake ID, step IDs, catch-up flag)
and `bread_assistant_updated` (bake ID, revision, cause) on the HA bus. No notification
capabilities or large snapshots are placed on the bus or entity state.

## Done has no effect / step is unavailable

Check the displayed bake ID, step prerequisites and lifecycle. Paused/canceled bakes
cannot advance. A stale phone capability is deliberately ignored after snooze,
adjustment, pause, completion or a new bake. Use the latest notification or dashboard.
Readiness is never inferred from time; a prerequisite may need manual confirmation.
The completion button waits for its displayed due time. Biological checkpoints
can be confirmed earlier through `complete_step`; fixed timers enforce their
minimum duration (15 minutes for the uncovered stage, 20 for covered baking).

## Dashboard shows unavailable entities or missing cards

Check that the integration loaded, compare actual entity IDs with the YAML and
update references after language-specific naming or collisions. No HACS components
are required. In paused state controls are unavailable while current-step/timeline
information remains visible. Local times follow HA Settings → System → General;
all persisted timestamps remain UTC. Confirm notification dashboard path if using
a different dashboard URL.

## Storage write fails

No user transition is published until it is saved. Resolve the HA filesystem/free
space problem, then retry the action. Deadline callbacks retry storage failures
after one minute and expose an error in the status sensor. No state writes depend
on a shutdown-only save. Push reservation precedes external delivery; a crash in
that small interval can delay a push until the next configured reminder interval.

## Logging and Recorder

Merge this into your existing logger configuration for a staging investigation:

```yaml
logger:
  logs:
    custom_components.bread_assistant: debug
```

Logs report recalculation causes and delivery failures. Avoid sharing private HA
storage, mobile action tokens, secrets or your full config. For long-running installs
you may exclude `sensor.bread_assistant_current_step` from Recorder to reduce
timeline attribute history; it does not affect bake persistence or the dashboard:

```yaml
recorder:
  exclude:
    entities:
      - sensor.bread_assistant_current_step
```

Merge exclusions with your existing Recorder settings; do not replace them.
