# Install and operate

This repository contains copy-ready files. It does not change your running Home
Assistant, Compose services, network, secrets or automations. Test on staging
first. The tested baseline is HA Core 2026.10.4 with Python 3.14.2; other HA releases
have not been verified here. Check your version under Settings → About.

## Installation in an existing Docker config mount

1. Inspect your existing Compose `volumes` mapping to locate the host directory
   mounted at `/config`. Keep the mapping and container configuration unchanged.
2. Back up that entire config directory, including `.storage`, while HA is stopped
   or using your established consistent HA backup procedure. Keep a matching copy
   of any previous integration version for rollback.
3. Copy `custom_components/bread_assistant/` from this repository into
   `<config>/custom_components/bread_assistant/`, including recipes, manifest,
   translations and services metadata. Do not copy `.tools`, tests or Python
   environments. No `pip install` is needed on HA; there are no runtime requirements.
4. Restart **staging** HA. Open Settings → Devices & Services → Add Integration →
   Bread Assistant. A second instance is intentionally blocked.
5. Select your existing iPhone `notify.mobile_app_*` destination or leave it empty.
   The app must already be registered with HA. You can change this later through
   Configure. Enable/disable push and choose a 5–240 minute repeat interval,
   dashboard path and 12/24-hour display preference.
   Optional iOS Live Activities have their own enable toggle and iPhone destination;
   see [requirements and configuration](../README.md#ios-live-activities-optional).
   Regular actionable reminders remain independently configurable.
6. Follow the staging checklist below. Apply the same files to production only
   through your own backup/deployment process after staging passes.

No integration YAML entry, extra containers, database or network access is needed
for production. The manifest omits documentation/issue URLs because this repository
has no known published project URL; local documentation is linked from README.

## Baking dashboard

Copy `dashboards/bread_assistant.yaml` to
`<config>/dashboards/bread_assistant.yaml`. Merge this example into your existing
`lovelace` configuration; preserve all existing dashboard entries:

```yaml
lovelace:
  dashboards:
    bread-assistant:
      mode: yaml
      title: Bread Assistant
      icon: mdi:bread-slice
      show_in_sidebar: true
      filename: dashboards/bread_assistant.yaml
```

Restart/reload HA as your existing YAML configuration requires. The resulting path
is `/bread-assistant/overview`, matching the default notification link. Alternatively,
create a new storage dashboard, open its raw configuration editor and paste the
provided YAML. Set the corresponding dashboard path in integration options.

The integration serves and loads `custom:bread-assistant-card` automatically when
HA's HTTP and frontend integrations are enabled. Copy the entire integration,
including its `frontend/` folder, for manual or HACS installation. No button-card,
layout-card, card-mod or custom theme is required. Restart staging HA after an
upgrade and refresh the browser/Companion frontend cache if the old card persists.

This workspace's YAML uses `entity_prefix: kitchen_bread_assistant`. For default
registry names, change it to `bread_assistant`. Inspect your sensors in Developer
Tools → States. For individually renamed sensors, override only the relevant keys:

```yaml
type: custom:bread-assistant-card
entity_prefix: bread_assistant
entities:
  status: sensor.my_bake_status
  current_step: sensor.my_current_baking_step
```

The other supported keys are `next_step`, `next_due`, `progress`, `overdue_count`.
Actions use the canonical Bread Assistant services with captured bake/step IDs;
button entity names do not need configuring. The panel view uses the whole available
width; the card also works inside existing sections or other Lovelace views.
It stacks at 760px available card width, including on iPhone 16 Pro (402 CSS px).

For frontend configurations that do not load the module automatically, add this
**JavaScript module** under Settings → Dashboards → Resources (advanced mode), or
merge it into `lovelace.resources` when resources are managed in YAML:

```yaml
url: /bread_assistant/frontend/bread-assistant-card.js?v=1
type: module
```

Use one registration method. The HTTP integration must be enabled to serve assets.
If you prefer entirely built-in cards, install
`dashboards/bread_assistant_native.yaml` instead; adjust its entity references in
both cards and Jinja templates. Existing dashboards and automations keep working.

## Starting and progressing a bake

Use **Feed starter** for a normal bake. Confirm feeding, follow reminders and
manually assess starter readiness. Use **Prepared starter** to intentionally skip
feeding and begin autolyse immediately. You must still confirm starter readiness.
Complete the autolyse checkpoint before kneading. **Done / Confirm ready** acts on
the current named step; **Remind in 10 min** changes reminders only. These controls
are unavailable while paused or before their target is due. Developer Tools →
Actions allows individual step confirmation, including early biological readiness.

Pause reminders only when appropriate; dough and oven processes continue. Resume
to review overdue estimates. Cancel archives a summary and stops further alerts.
After the cooling checkpoint the bake completes; then you can start another.

The source recipe is [Justyna Dragan's basic wheat sourdough](https://justynadragan.pl/2020/08/podstawowy-chleb-pszenny-na-zakwasie.html).
Instructions here are concise original guidance; consult the full method for
technique. The bundled recipe makes one small loaf. **Use dry heatproof gloves for
250 °C cast iron, watch for steam and keep hot lids on a safe surface.**

## Canonical actions

Start with feeding:

```yaml
action: bread_assistant.start_bake
data:
  recipe_id: justyna_basic_wheat_sourdough
  starter_workflow: feed
```

Start with a prepared starter and optional opaque starter reference:

```yaml
action: bread_assistant.start_bake
data:
  starter_workflow: prepared
  starter_id: kitchen-wheat
  starter_ready: true  # only if YOU explicitly confirm readiness now
```

Omit `starter_ready` to retain the open manual checkpoint. Omit `starter_id` if
unlinked; no Starter Manager is installed or required. Optional `start_time` must
be ISO-8601 with an explicit offset, e.g. `2026-11-14T11:00:00+01:00`.

Copy the active bake ID from the dashboard or the status sensor's `bake_id`
attribute. Use it with the stable step IDs shown in the timeline:

```yaml
action: bread_assistant.complete_step
data:
  bake_id: REPLACE_WITH_ACTIVE_UUID
  step_id: starter_ready
```

```yaml
action: bread_assistant.snooze_step
data:
  bake_id: REPLACE_WITH_ACTIVE_UUID
  step_id: bulk_ready
  minutes: 10
```

```yaml
action: bread_assistant.adjust_step
data:
  bake_id: REPLACE_WITH_ACTIVE_UUID
  step_id: bulk_ready
  due_at: "2026-11-14T21:00:00+01:00"
```

`adjust_step` sets a requested earliest deadline; prerequisite and minimum timer
constraints still apply. `pause_bake`, `resume_bake` and `cancel_bake` each require
`bake_id`. All schemas reject unknown fields. Step mutation actions require both
bake and step IDs. Old/canceled bake IDs cannot modify the current workflow.

## Staging acceptance checklist

- Start both workflows. Check the planned 12 milestone offsets and prepared
  workflow changes; inspect all readiness gates and the two oven stages.
- Confirm a step 17 minutes late and compare actual versus planned/dependent due
  times. Snooze and verify that process due times do not move.
- Restart during cold proof. Verify retained progress, one catch-up notification
  and correct UTC/local timestamps. Try Pause/Resume and Cancel.
- On an actual iPhone, permit notifications, long-press to see Done/Snooze, and
  test app foregrounded, backgrounded and closed. Verify the dashboard link.
  If you use remote access, verify connectivity in your normal setup
  without changing network settings for this integration.
- Tap an old notification, tap Done twice, and verify no unintended transition.
- Check iPhone and desktop dashboard rendering and entity IDs. Review HA logs
  for errors before considering production deployment.

## Backup, upgrade, rollback and removal

Bake state lives in HA-managed `.storage/bread_assistant.bakes`. Do not edit it while
HA runs. Back up `.storage` with your entire HA config. Schema v1 migrates to v2
automatically; older bakes gain an empty starter reference without changing the
recipe snapshot. Future unsupported versions fail safely rather than being
overwritten. A downgrade requires restoring the matching pre-upgrade storage backup
and integration files while HA is stopped. Never hand-edit only the version number.

To remove: cancel the active bake, remove the config entry in Devices & Services,
then remove the dashboard registration/file and integration directory during your
maintenance window. Storage is intentionally retained on entry deletion so an
accidental removal does not erase a bake. For full erasure, back up first, stop HA
and remove **only** `.storage/bread_assistant.bakes`; keep other HA storage intact.
