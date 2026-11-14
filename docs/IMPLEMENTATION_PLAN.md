# Bread Assistant — Home Assistant Custom Integration

## Implementation plan for Codex

**Status:** implementation specification  
**Target:** Home Assistant, Home Assistant 2026.x  
**Language:** Python 3, asynchronous Home Assistant APIs  
**Integration domain:** `bread_assistant`  
**Primary UI:** native Home Assistant Lovelace dashboard  
**Primary notification client:** Home Assistant Companion App on iPhone  
**Initial locale:** English in code; Polish labels/translations where supported  
**First recipe:** Justyna Dragan, *Podstawowy chleb pszenny na zakwasie*  
**Recipe URL:** https://justynadragan.pl/2020/08/podstawowy-chleb-pszenny-na-zakwasie.html

## 1. Goal

Create a local-first, restart-safe Home Assistant custom integration that guides a person through a sourdough bread bake. The user starts a bake from HA, sees a timeline and current step, gets actionable mobile notifications, records actual completion times, and can delay steps without corrupting dependent scheduling.

The system must not assume sourdough fermentation is ready simply because a timer elapsed. Treat durations as estimates and readiness as a manual checkpoint.

### MVP acceptance scenario

1. Install the custom integration in a test HA instance and configure it using **Settings → Devices & Services**.
2. Open a dedicated Bread Assistant dashboard and start the included recipe now.
3. See the 12 chronological reference milestones and detailed substeps, actual vs planned times, current step, next due item, and overall progress.
4. Receive a push reminder on the chosen iPhone when an action becomes due.
5. Tap **Done** or **Remind in 10 minutes** from the notification. The action updates the corresponding bake and step, not some other notification.
6. Complete an activity 17 minutes late and observe its genuinely dependent downstream steps shift accordingly; independent/planned tasks do not move unless required by an explicit dependency or user decision.
7. Restart Home Assistant during the bake. Verify the bake state, completed steps, next reminders, and notifications recover without duplicates or reminder storms.
8. Pause, resume, and cancel a bake. Completed and canceled bakes do not emit subsequent alerts.
9. Start a new bake after finishing/canceling the previous one.

## 2. Scope

### Must have (MVP)
- Config flow for setup, one config entry, and options flow for notification target, reminder behavior, and local display preferences.
- Included versioned starter recipe with chronological reference milestones and additional optional technique checkpoints.
- One active bake at a time; preserve archived summaries of completed/canceled bakes in storage.
- `start_bake`, `complete_step`, `snooze_step`, `pause_bake`, `resume_bake`, `cancel_bake`, and `adjust_step` HA actions.
- Timestamp-based, dynamically recomputed step deadlines with explicit dependency semantics.
- Manual readiness checkpoints for starter readiness and fermentation/proofing.
- Native sensor and button entities for the dashboard, with useful diagnostic attributes (keep attributes bounded; do not dump large histories into HA state).
- iOS push notifications with Done / Snooze actions and links to the dashboard.
- Persistent state, safe reloading, shutdown cleanup, and overdue handling.
- Custom HA dashboard YAML using only built-in cards/components for MVP; optional HACS cards must not be required.
- Automated tests and a repeatable local development environment.

### Not in MVP
- External .NET API, PostgreSQL, MQTT broker, cloud service, separate web frontend, or AppDaemon.
- Automated machine-vision proof assessment, computed fermentation readiness, recipe scraping at runtime, Apple Live Activities, multi-user concurrent editing, photo upload, and multi-bake concurrency.
- Auto-starting an oven, automatically changing oven temperature, or claiming baking is complete without user input.

### Later
- Multiple editable recipes and import/export (v2).
- Photo journal and performance analytics (v2).
- Optional kitchen temperature Zigbee sensor and graphing (v2).
- "Finish at X" backward planning with readiness uncertainty explicitly displayed (v3).
- Optional SQLite only when queries across many archived bakes genuinely require it; do not write directly to HA Recorder's database.

## 3. Architectural decisions

### 3.1 Deployment

Install `custom_components/bread_assistant/` in the configuration directory of an existing Home Assistant installation. No additional service is necessary for production. Test on staging before changing production. Recommend backing up the HA configuration directory before installing or upgrading the integration.

### 3.2 Logical architecture

```text
Lovelace dashboard ────> HA actions / button entities
        │                           │
        └────────> sensors <────────┤
                                    ▼
                             BakeCoordinator
                          (serializes mutations)
                            │       │       │
                            ▼       ▼       ▼
                       Recipe    Scheduler  Notifications
                       Catalog   (HA time  (HA Companion
                       (bundled) callbacks) App)
                            │       │       │
                            └───────┴───────┘
                                    ▼
                          HA Store (.storage/)
                                    │
                                    ▼
                       HA Event Bus / Recorder
```

- **Recipe catalog:** versioned local JSON/YAML files, read and validated at setup; immutable snapshot copied into each bake when started. Loading user-authored recipes can be deferred until v2.
- **Domain engine:** pure Python immutable-ish models and deterministic schedule calculations; no HA imports inside core scheduling logic. Clock injected for tests.
- **Coordinator:** HA-aware runtime object for active bake, async locking, state changes, event publishing, storage, timers and entity updates. Use a coordinator that fits HA conventions; do **not** poll on a fixed interval just to recompute countdown.
- **Scheduler:** use HA event/time helpers and UTC-aware `datetime`; schedule callbacks for the next deadline and recreate them after every mutation/reload. UI countdown can use HA timestamp entities and native relative-time display, without per-second writes.
- **Persistence:** `homeassistant.helpers.storage.Store` with schema versioning and safe serialized writes; HA owns `.storage`. No SQLite in MVP.
- **Notifications:** use an explicitly configured mobile notify action, and process `mobile_app_notification_action` events with bake/step/action identifiers. Validate payload against current state.
- **Entities/actions:** integration owns sensors and controls and registers namespaced actions in `async_setup`, forwarding to the active coordinator. The integration should tolerate setup with no mobile app connected.

### 3.3 State model

```text
BakeStatus: idle | active | paused | completed | canceled
StepStatus: pending | ready | in_progress | done | skipped
StepKind:  action | timer | checkpoint | milestone
DependencyKind: after_start | after_completion | parallel_anchor | absolute
```

Suggested models:

```python
RecipeDefinition(id, version, title, url, ingredients, steps)
StepDefinition(id, title, kind, instructions, prerequisites,
               offset_minutes, duration_minutes, dependency_kind,
               requires_confirmation, alert_policy, optional)
BakeRun(id, recipe_id, recipe_version, recipe_snapshot,
        started_at, status, pause_started_at, archived_at,
        step_runs, notes, revision)
StepRun(step_id, status, planned_at, due_at, started_at,
        completed_at, snoozed_until, acknowledged_at,
        notification_generation, notes)
```

Use UUIDs for bake ids; stable human-readable step ids. All persisted timestamps must be UTC ISO-8601 with offsets. Convert to HA's local timezone for rendering, accounting for midnight and DST. Use explicit `revision` or mutation generation to reject stale notification actions.

### 3.4 Scheduling rules (important)

1. The **reference schedule** is a set of milestone target offsets relative to an 11:00 example, not a claim about biological readiness.
2. Each step declares its anchor and dependency, never just a globally shifted offset.
3. For a fixed-duration step, downstream steps anchored to its **actual completion** move if completion runs late.
4. For a **parallel** activity (starter maturation overlapping autolyse), completing one activity must **not** automatically shift every other activity. Kneading requires both autolyse completed and starter manually marked ready.
5. Manual checkpoints become ready at an estimate, then stay open until confirmed. Do not auto-complete.
6. The first and second folds anchor to the **actual bulk fermentation start** at +30 and +60 minutes (not necessarily +30 minutes after the first fold was marked done).
7. Pre-shaping can be suggested at the expected bulk-fermentation end but should require a readiness decision. Final shaping follows **actual pre-shape completion** with a 10-minute rest.
8. Cold proofing is a window with a recommended target, not a hard automatic release. Preheating can run while the loaf is proofing; baking requires oven-ready and dough-ready confirmations.
9. Covered bake is 20 minutes at 250 °C; uncovered bake is 15–20 minutes at 230 °C; notifications and stage transitions must model both segments, rather than treating 35–40 minutes as an opaque timer.
10. Snoozing **only a reminder** must not mutate process time or dependencies. Changing schedule requires explicit `adjust_step` or actual start/completion events.
11. Distinguish `planned_at`, `due_at`, and `actual_*`; preserve original plan for variance analysis.
12. Prevent repeated Done/Skip/Snooze calls from double-advancing, and prevent stale action IDs from changing another bake.
13. Pausing freezes reminders. Define whether timers are wall-clock or active-time for each step: fermentation and cold proof continue in real life when HA is paused. Therefore never silently freeze biological process time; on resume, recompute from real timestamps and warn about overdue readiness checks.
14. After restart, reconcile overdue items and issue at most **one consolidated catch-up notification** per bake, not one alert for each missed timer.
15. Use one centralized scheduling mechanism; no accumulation of old callbacks after rescheduling.

## 4. First recipe definition

Seed source: https://justynadragan.pl/2020/08/podstawowy-chleb-pszenny-na-zakwasie.html

Reference 11:00 day 1 to 09:00 day 2. Extracted milestones and relative offsets:

| ID | Time | Offset from start | Step |
|---|---|---:|---|
| `feed_starter` | D1 11:00 | 0 | Feed starter |
| `autolyse_start` | D1 14:00 | 180 | Start autolyse |
| `knead_start` | D1 15:00 | 240 | Begin kneading |
| `bulk_start` | D1 15:05 | 245 | Begin bulk fermentation |
| `fold_1` | D1 15:35 | 275 | First stretch-and-fold |
| `fold_2` | D1 16:05 | 305 | Second stretch-and-fold |
| `preshape` | D1 20:05 | 545 | Pre-shape |
| `final_shape` | D1 20:15 | 555 | Final shape |
| `cold_proof_start` | D1 20:20 | 560 | Refrigerate shaped dough |
| `preheat_oven` | D2 07:40 | 1240 | Preheat oven and cast iron |
| `bake_start` | D2 08:20 | 1280 | Begin baking |
| `bake_finish` | D2 09:00 | 1320 | Remove loaf |

Note: the author's text describes starter activation often taking **4–5 hours**, even though the illustration places autolyse at +3 hours. Do not treat the example's fixed offsets as proof of starter readiness. Cold proof from 20:20 to 08:20 is exactly 12 hours; preheat begins at 07:40 while proof continues. The original overview lists 35–40 minutes of baking.

Add separate *optional/substep* items for `starter_ready`, `autolyse_complete`, `bulk_ready`, `oven_ready`, `dough_ready`, `score_loaf`, `remove_lid`, `cooling_start`, and `cooling_check` as needed to make guidance accurate, without altering the 12 reference milestones. Avoid unnecessarily annoying push alerts for every optional substep.

Ingredient snapshot (one small loaf):
- Starter feeding: 40 g refrigerated starter, 40 g whole wheat flour, 40 g wheat bread flour type 750, 80 g water.
- Dough: 350 g wheat bread flour type 750, 235 g water (32–35 °C), 120 g active fed starter, 10 g salt.
- Accessories: olive oil, rice flour for basket, bench flour, parchment, proofing basket, Dutch oven / cast iron pot, gloves, cooling rack.

Bake-step descriptions must be **original concise paraphrases**, with attribution and a link to the author's full method; don't copy an article wholesale. Include safety copy about handling 250 °C cast iron and avoiding burns.

## 5. Home Assistant API surface

Suggested supported entities (names will be assigned by HA, use unique IDs and device registry metadata):

| Type | Suggested entity | State / usage |
|---|---|---|
| sensor | `sensor.bread_assistant_status` | idle / active / paused / completed / canceled |
| sensor | `sensor.bread_assistant_current_step` | step title; attrs: ID, short instructions, status |
| sensor | `sensor.bread_assistant_next_step` | step title |
| sensor | `sensor.bread_assistant_next_due` | aware datetime; `device_class: timestamp` |
| sensor | `sensor.bread_assistant_progress` | percent of required workflow completed |
| sensor | `sensor.bread_assistant_overdue_count` | number of outstanding overdue steps |
| button | `button.bread_assistant_start` | start default recipe (only if idle/completed/canceled) |
| button | `button.bread_assistant_complete_current` | mark actionable current step done |
| button | `button.bread_assistant_pause` | pause |
| button | `button.bread_assistant_resume` | resume |
| button | `button.bread_assistant_cancel` | cancel |

HA **actions** have richer parameters and are the canonical API. Example `services.yaml` contract:

```yaml
start_bake:
  fields:
    recipe_id:
      required: false
      example: justyna_basic_wheat_sourdough
    start_time:
      required: false
      example: "2026-11-14T11:00:00+01:00"
complete_step:
  fields:
    bake_id:
      required: true
    step_id:
      required: true
snooze_step:
  fields:
    bake_id:
      required: true
    step_id:
      required: true
    minutes:
      required: true
adjust_step:
  fields:
    bake_id:
      required: true
    step_id:
      required: true
    due_at:
      required: true
```

Implement any additional action schemas explicitly. Validate required IDs, datetime parsing, lifecycle, values/ranges, and domain errors; report meaningful `HomeAssistantError`s. Register the service action handlers during `async_setup`, not only `async_setup_entry`, following current HA guidelines. Confirm any exact API signatures against the matching HA Core version.

Expose a compact timeline through sensor attributes (e.g. next 12–20 steps, each with ID, title, state, due ISO datetime, completed ISO datetime), or via a dedicated supported HA action response if attribute size/Recorder churn would be problematic. Do not create a sensor per bake step unless required for better native card interactions.

## 6. Notifications

- Options flow: select an available, user-authorized mobile notification destination. Validate action existence and handle missing/unavailable target without breaking the bake.
- On due step, send mobile push with step title, abbreviated instructions, **Done**, **Remind in 10 min** and dashboard URL.
- Action identifiers should include a private, non-guessable bake-specific token and step/generation mapping held by the coordinator, or validated opaque random IDs. Never trust raw `step_id` alone.
- Listen for `mobile_app_notification_action`. Verify matching active bake, generation, pending step, and known action. Make handlers idempotent.
- Use unique notification tags or generations; if updating/replacing notices, verify mobile support.
- Rate-limit reminders. Use `snoozed_until` for notification delivery only, not fermentation timing.
- At HA startup, reconcile and send at most one summary notification if tasks became overdue while down.
- Optional: HA `persistent_notification` fallback and event bus event on reminder; log errors without disabling engine.
- Make notification content short and actionable; include burn safety warning when handling hot cast iron.

## 7. Dashboard UX

Ship a working native-only example `dashboards/bread_assistant.yaml` and installation instructions. Use modern built-in Tile, Markdown, Entities, conditional, and history cards only where they are truly supported in the target HA version. If a card cannot directly consume service response data, render the timeline from a bounded sensor attribute template (or use explicit step entities); do not claim arbitrary YAML can call services interactively.

Desired view sections:

1. **Header:** Bread Assistant, recipe title, lifecycle state, start/cancel button(s).
2. **Current step:** clear large title, due/local time, original short instructions, Done and Snooze actions.
3. **Next action:** next due timestamp; native relative-time display. Do not update sensors every second.
4. **Timeline:** steps, state, expected and actual completion, visual distinction for done, ready, overdue, future.
5. **Recipe:** ingredients, source link, compact technique details, safety.
6. **Status:** progress, current bake id, late tasks, paused state, last sync/error.

The dashboard must be usable on iPhone and desktop. Prefer native cards first; optional advanced visuals can be a later iteration.

## 8. Suggested repository structure

```text
bread-assistant/
├── AGENTS.md
├── IMPLEMENTATION_PLAN.md
├── README.md
├── pyproject.toml
├── custom_components/
│   └── bread_assistant/
│       ├── __init__.py
│       ├── manifest.json
│       ├── const.py
│       ├── config_flow.py
│       ├── coordinator.py
│       ├── models.py
│       ├── recipe_catalog.py
│       ├── scheduler.py
│       ├── storage.py
│       ├── notifications.py
│       ├── sensor.py
│       ├── button.py
│       ├── services.yaml
│       ├── strings.json
│       ├── translations/
│       │   ├── en.json
│       │   └── pl.json
│       └── recipes/
│           └── justyna_basic_wheat_sourdough.json
├── dashboards/
│   └── bread_assistant.yaml
├── tests/
│   ├── conftest.py
│   ├── test_recipe.py
│   ├── test_schedule.py
│   ├── test_coordinator.py
│   ├── test_actions.py
│   ├── test_notifications.py
│   ├── test_storage.py
│   └── test_config_flow.py
└── docs/
    ├── architecture.md
    ├── deployment.md
    └── troubleshooting.md
```

Keep the domain engine decoupled from Home Assistant, and all IO/side effects behind adapters. Resist overengineering with microservices or an ORM.

## 9. Step-by-step implementation tasks

### Phase 0 — Inspect and validate environment

- [ ] **P0.1** Inspect existing repository structure and HA Docker Compose/config volume paths. Do not assume or overwrite user config.
- [x] **P0.2** Determine installed HA Core version and supported Python version; consult current HA developer documentation for integration lifecycle, services, config flow, storage, entity APIs, event/time helpers, and translations.
- [ ] **P0.3** Determine available `notify.mobile_app_*` action for the iPhone; do not hardcode the user's actual device name into source control.
- [x] **P0.4** Create `README.md`, local dev/test instructions, `.gitignore` and `pyproject.toml` with lint/format/test dependencies.
- [x] **P0.5** Decide whether testing will use `pytest-homeassistant-custom-component` and pin compatible versions.

**Done when:** contributor can run unit tests locally and understands deployment mount; no production change yet.

### Phase 1 — Integration skeleton

- [x] **P1.1** Implement `manifest.json` (`domain`, `name`, `version`, `documentation`, `issue_tracker` if real, `config_flow: true`, appropriate `iot_class`, dependencies if needed). Never invent published URLs.
- [x] **P1.2** Implement async config flow and options flow with user-friendly errors and proper single-instance behavior.
- [x] **P1.3** Implement `async_setup`, `async_setup_entry`, `async_unload_entry` and cleanup; forward sensor/button platforms.
- [x] **P1.4** Register actions during `async_setup` with schema validation and handle missing/unloaded entries correctly.
- [x] **P1.5** Add translation strings and baseline config flow tests.

**Done when:** integration can be installed, configured, reloaded and unloaded without HA errors.

### Phase 2 — Domain, recipe and deterministic schedule

- [x] **P2.1** Implement validated dataclasses or equivalent typed models for recipe, step, bake, dependencies and timestamps.
- [x] **P2.2** Bundle the first recipe's ingredient list, 12 reference milestones, original concise instructions, readiness checkpoints, and two baking phases.
- [x] **P2.3** Implement dependency-graph validation: no unknown IDs, cycles, negative durations, ambiguous anchors, or duplicated IDs.
- [x] **P2.4** Write the scheduling engine as pure functions: initial schedule, transition on start/complete, dependency recompute, adjust, snooze, pause/resume reconciliation.
- [x] **P2.5** Enforce gate semantics: starter readiness + completed autolyse before kneading, bulk ready before pre-shape, oven + dough ready before baking.
- [x] **P2.6** Add time-zone and overnight scenarios, offset tests, out-of-order completion tests, and clock-controlled tests.

**Done when:** all 12 reference offsets match the article, independent stages are not globally shifted, and schedule tests pass.

### Phase 3 — Persistence and runtime coordination

- [x] **P3.1** Implement HA Store adapter, JSON schema version, serialization and migration hook.
- [x] **P3.2** Implement coordinator with `asyncio.Lock` guarding mutations, idempotence, and event listeners for state changes.
- [x] **P3.3** Persist on meaningful transitions; batch or debounce writes where appropriate but ensure completion isn't lost on restart.
- [x] **P3.4** Implement deadline scheduling and cancellation. Rebuild timers after load, options change, pause/resume and step completion.
- [x] **P3.5** Reconcile overdue tasks on restart and avoid alert storms. Handle backup restore with old/unknown storage version safely.
- [x] **P3.6** Emit useful `bread_assistant_*` HA bus events, without putting sensitive or large data in attributes.

**Done when:** restart mid-bake preserves progress and does not double-trigger a reminder.

### Phase 4 — Native entities and actions

- [x] **P4.1** Create a single integration device with stable unique IDs and availability behavior.
- [x] **P4.2** Implement required sensor and timestamp entities; use entity descriptions, properties, update callbacks and correct device classes.
- [x] **P4.3** Implement button actions with honest availability based on bake state.
- [x] **P4.4** Implement canonical service actions and argument validation. Include step-level actions requiring bake and step ids.
- [x] **P4.5** Add service-action metadata in `services.yaml` and docs/examples.
- [x] **P4.6** Test unauthorized/stale/duplicate/invalid actions and inactive bake handling.

**Done when:** all actions work in Developer Tools → Actions and entities respond immediately.

### Phase 5 — Companion notifications

- [x] **P5.1** Add configurable notification target and optional disable toggle.
- [x] **P5.2** Implement due reminders using supported HA notification actions, category/tag data and dashboard deep links.
- [x] **P5.3** Implement secure-ish, opaque action correlation for notification buttons and register a single event listener per integration entry.
- [x] **P5.4** Implement Done and Snooze flows, retries/error logging and duplicate event handling.
- [x] **P5.5** Implement consolidated catch-up reminders after downtime.
- [ ] **P5.6** Validate on a real iPhone, including Home Assistant Companion backgrounded/closed and remote connectivity where relevant.

**Done when:** notification buttons change only the intended current step and stale notification buttons cannot change a new bake.

### Phase 6 — Dashboard

- [x] **P6.1** Provide a native Lovelace dashboard YAML file and a clear registration/import guide for a Docker HA installation.
- [x] **P6.2** Build status, current-step, next-step, progress and actionable control sections.
- [x] **P6.3** Render the full reference timeline with planned and actual times and overdue highlights, using a supported built-in approach.
- [x] **P6.4** Add recipes/ingredients/instructions and source attribution, plus cast-iron safety message.
- [ ] **P6.5** Test mobile screen width and desktop layout; verify all native cards render on the installed HA version.

**Done when:** a user can perform a complete bake using only the HA dashboard and iPhone reminders.

### Phase 7 — Quality and release

- [x] **P7.1** Run Ruff lint/format, mypy or equivalent targeted type validation, pytest, and HA-specific test fixtures.
- [x] **P7.2** Add scenario tests: midnight, DST boundary, 17-minute lateness, concurrent Done buttons, stale IDs, shutdown while a callback is pending, storage corruption, no phone configured, unavailability, cancel and restart.
- [x] **P7.3** Document how to install in Docker Compose, enable debug logging, migrate storage, back up `.storage`, and uninstall safely.
- [ ] **P7.4** Smoke-test on staging HA; then deploy to production with an explicit backup/rollback plan.
- [x] **P7.5** Record actual tested versions and known limitations in README; deliver a short final implementation report with commands run and results.

**Done when:** all MVP acceptance scenarios pass; no unsupported claims, no unexplained HA log errors.

## 10. Test matrix

| Scenario | Expected behavior |
|---|---|
| Start at 11:00 local time | Reference offsets match D1 and D2 milestone times |
| Start at 18:35 | Overnight timestamps roll to correct dates |
| Starter not ready at 15:00 | Kneading remains gated, a readiness alert is available, no forced transition |
| Autolyse finished 17 min late | Kneading gated until both prerequisites done; only genuinely dependent tasks shift |
| First fold done late | Second fold remains anchored to bulk start +60 min unless explicitly changed |
| Snooze 10 min | Reminder shifts, process due time does not |
| Two notification Done taps | One state transition, no duplicate next step |
| Tap notification from previous bake | Ignored and logged at debug level |
| HA reboot while proofing | State and wall-clock fermentation preserved; no reminder storm |
| Pause overnight | No push while paused; actual proof time still passes; resume warning |
| Phone notify action missing | Bake keeps running; warning visible in logs/state; no crash |
| DST transition | Internal UTC timestamps correct; UI shows HA local times |
| Cancel active bake | All pending callbacks canceled; cannot complete canceled bake |
| Completion of final step | Bake becomes completed and no new process notifications fire |

## 11. Implementation constraints and code standards

- Follow the installed HA Core version's documented APIs; when docs conflict with examples, prioritize official developer docs and actual tests.
- Keep scheduling and persistence operations asynchronous as needed; never block the HA event loop with disk IO.
- Do not store uncontrolled article HTML or scrape the blog at runtime.
- No secrets, phone service identifiers, IP addresses, auth tokens, or absolute user-specific paths in Git.
- Avoid `time.sleep`, naive datetimes, polling loops, unbounded attributes, and setting entities to fake states.
- No background work outside the HA integration lifecycle; cancel callbacks and unsubscribe event listeners on unload.
- Explicitly log schedule calculation causes; add debug logs that make it easy to understand why a deadline moved.
- Recheck actual HA action/service syntax before implementing examples verbatim.
- Preserve completed timestamps and original plan; store changes as explicit mutations rather than rewriting history.
- Maintain a narrow stable API for future UI work.

## 12. Codex execution protocol

1. Read `AGENTS.md` and this document completely.
2. Inspect repository and actual HA version before choosing implementation details.
3. Implement phases in order; keep each phase as a coherent, testable change.
4. After each phase: run tests/lint, fix issues, update a concise progress section in README, and continue if there are no blockers.
5. Do not stop at planning or scaffolding: implement the working MVP end to end.
6. Where specs conflict with the article, preserve the article's reference timeline but choose safety and manual fermentation readiness over automatic completion; document assumptions.
7. Never modify the production HA config, Docker Compose files or network configuration without the user's explicit authorization. Produce copy-ready files and deployment instructions first.
8. End with a report listing implemented features, tests/results, manual setup steps, and remaining limitations.

## 13. Official documentation links

- HA developer overview: https://developers.home-assistant.io/
- HA integration actions: https://developers.home-assistant.io/docs/dev_101_services/
- HA mobile actionable notifications: https://companion.home-assistant.io/docs/notifications/actionable-notifications/
- HA mobile basic notifications: https://companion.home-assistant.io/docs/notifications/notifications-basic/
- Original recipe: https://justynadragan.pl/2020/08/podstawowy-chleb-pszenny-na-zakwasie.html

## Implementation verification (14 November 2026)

Implemented MVP and automated checks: see [phase verification report](implementation_checklist.md).
Unchecked items require the actual HA mount, physical iPhone or browser staging.
P7.4 production deployment is intentionally excluded by the user instruction.
Verified baseline: HA 2026.10.4, Python 3.14.2; 46 tests passed, 91% coverage,
Ruff lint/format and targeted strict mypy passed. Production was not contacted.
