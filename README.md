# Bread Assistant

Local-first Home Assistant custom integration for one sourdough bake at a time.
Implementation specification: [implementation plan](docs/IMPLEMENTATION_PLAN.md).

Start a bake, follow a dependency-aware timeline, confirm biological readiness,
and receive actionable Companion reminders. Feed a starter during the bake or use
one already prepared. No phone, Starter Manager, database or external service is
required. Bake snapshots survive restarts and recipe upgrades.

- [Installation, dashboard and action examples](docs/deployment.md)
- [Architecture and future Starter Manager boundary](docs/architecture.md)
- [Troubleshooting, backups and logging](docs/troubleshooting.md)
- [Phase checklist and verification report](docs/implementation_checklist.md)

Quick install: copy `custom_components/bread_assistant` into your staging HA config,
restart HA and add **Bread Assistant** in Devices & Services. Install the bundled
[dashboard YAML](dashboards/bread_assistant.yaml) using the linked deployment guide.
The repository does not deploy to production.

## English and Polish

Open **Settings → Devices & Services → Bread Assistant → Configure → Backend
content language** (Polish: **Język treści integracji**). Choose:

- **Automatic** (`auto`, the default): use the Home Assistant **system** language.
- **English** (`en`) or **Polish** (`pl`): override the language of recipes,
  instructions, dashboard Markdown, reminders, and Live Activities.

Unsupported system languages fall back to English. Regional variants such as
`pl-PL` use Polish. Saving preferences safely reloads the integration: active bake
progress, actual timestamps, snoozes, IDs, and notification actions are retained.
Changing the system language in automatic mode refreshes backend presentation
without changing the bake. Previously delivered reminders are replaced at the next
reminder; language changes do not trigger an extra actionable push. Live Activities
use the current language on their next synchronization.

Home Assistant translates config/options forms, action descriptions, selectors,
entity names/states, errors, dialogs, and built-in controls through its
[native translation mechanism](https://developers.home-assistant.io/docs/internationalization/core/).
Native frontend controls use the language supported by Home Assistant for the
current profile. The backend language preference does not override profile settings.

The supplied dashboard uses a **bundled Lovelace card**, with no separate frontend
installation, personal theme or optional HACS plugin required. Its labels and
recipe content follow the integration language preference above. Dates use the
integration's 12/24-hour preference and HA system timezone. Native dialogs retain
the viewer's HA profile language. Multiple viewers share the recipe language;
backend-generated notifications also have no per-viewer language context.

Copy the updated [dashboard YAML](dashboards/bread_assistant.yaml) to obtain the
redesigned overview. Set `entity_prefix` to match your registered sensors;
this workspace's sample uses `kitchen_bread_assistant`. Existing dashboards and
automations continue using the same entity IDs, service names, and enum states.
Use `step_id` for automation logic rather than a translated step title.

All language and frontend assets ship inside `custom_components/bread_assistant`,
including HACS installs; no downloaded dictionaries or third-party cards are required.
See [the translation architecture and contributor guide](docs/architecture.md#translations)
for adding another language.

## Baking dashboard

The iOS-inspired overview includes a circular progress indicator, live countdown,
current stage, explicit completion and ten-minute reminder snooze, compact status
cards, and a timeline with completed, active, upcoming and overdue states. It shows
nearby steps first; **Show all steps** reveals the complete timeline and timestamps.
Ingredients, full current instructions, recipe attribution, oven safety and bake
diagnostics expand on demand. Idle, paused, completed, canceled, unavailable and
delivery/action error states include appropriate guidance and controls.

The card inherits HA colors, typography, borders, shadows and corner radius in a
shadow root, so its styles cannot affect other dashboards. Baking uses the theme's
warning amber; optionally set `bread-assistant-accent-color` in any theme. Both
standard light/dark themes and the supplied `Maciek iOS` dark reference work. The
reference only defines dark mode; light mode uses the active HA light theme.
Buttons have 48px minimum height, layouts adapt to the card's available width, and
animations honor reduced-motion settings. No countdown writes to HA state.

The original built-in-card dashboard remains available as
[bread_assistant_native.yaml](dashboards/bread_assistant_native.yaml). It retains
all controls and is usable without JavaScript from this integration. See the
[setup instructions](docs/deployment.md#baking-dashboard) and
[UI validation report](docs/ui-validation.md) for browser coverage and limitations.

## iOS Live Activities (optional)

Bread Assistant can keep the current bake on your iPhone Lock Screen and Dynamic
Island. It uses the official [Companion Live Activities API](https://companion.home-assistant.io/docs/notifications/live-activities/),
verified on 14 November 2026. Requirements: **iPhone with iOS 17.2+**, **HA Core
2026.7.0+**, and a Companion iOS release that provides Live Activities. Backend
tests use HA 2026.10.4; earlier Core versions have not been tested here. An iPhone
without Dynamic Island can show the Lock Screen activity. This feature targets
iPhone; iPad support is not claimed.

1. Register the iPhone with your staging HA server in Companion. Allow Live
   Activities in **iOS Settings → Home Assistant → Live Activities** (on newer iOS,
   find Home Assistant under **Apps**). Accept Companion's privacy disclosure.
2. In Companion, open **Settings → Live Activities** to check availability and
   inspect active activities. The API is documented as beta, so use a compatible
   app version if this setting is absent. Ensure the phone can reach HA, including
   when away from home: starting/updating requires a device-token handshake.
3. In HA, open **Settings → Devices & Services → Bread Assistant → Configure**.
   Turn on **Enable Live Activities (iOS)** and select your iPhone's
   `notify.mobile_app_*` action under **iPhone notification action for Live
   Activities**. The list contains mobile actions; select an iPhone, since service
   names alone do not identify its OS or permissions. Leave the target empty or
   the toggle off to operate without Live Activities. Defaults are off/empty.
4. Configure **Enable reminders** and **Mobile notification action** independently.
   Both channels can use the same phone or different phones. Done/Snooze buttons
   remain in regular reminders and the dashboard. Saving options reloads the
   integration and reconciles an existing bake without resetting its progress.

An activity starts with a bake and updates after step confirmation (including
regular notification Done actions), schedule adjustments, pause/resume, and a
deadline becoming due. Progress counts completed/skipped required steps, matching
the dashboard. The current step follows the dashboard's actionable-step order.
The countdown targets the step's process deadline; snoozing a reminder does not
move it. Pause removes the countdown and shows that process time continues. No
readiness checkpoint is automatically confirmed. Completion/cancellation clears
the activity; changing targets or disabling the option clears the old activity.

The integration sends `live_update: true` with the stable
`bread_assistant_live_<bake UUID>` tag, separate from the regular reminder tag.
For example, while waiting for the next action the integration produces a payload
like this (illustrative Unix timestamp and progress):

```yaml
action: notify.mobile_app_your_iphone
data:
  title: Bread Assistant
  message: "Start autolyse · Next action"
  data:
    tag: bread_assistant_live_12345678-1234-4234-8234-123456789abc
    live_update: true
    critical_text: Start autolyse
    progress: 1
    progress_max: 20
    chronometer: true
    when: 1794661200
    when_relative: false
    notification_icon: mdi:bread-slice
    silent: true
    url: /bread-assistant/overview
```

The end payload is `message: clear_notification` with only the matching `data.tag`.
Activity identities and start timestamps persist in HA Store as additive schema-v2
metadata; existing v1/v2 bakes load without it. Recovery sends the current snapshot
under the same tag, and retains failed cleanup across restarts and new bakes.
Failures appear in the status sensor's `live_activity_error` attribute and logs;
they do not replace regular reminder diagnostics or roll back a bake action.
Unavailable services and transport failures retry at a 15-minute deadline, or
when the selected service registers or a new bake action occurs.

Known limits:

- iOS expires each activity after at most eight hours. A single deadline renews
  it after 7 hours 55 minutes using clear/start with the same tag, including during
  overnight proofing or pause. Restart retains its age and renews an expired one.
  Renewal is best effort: iOS push-to-start budgets, offline phones and delivery
  delays can cause a gap. HA cannot confirm display/dismissal on the device.
- iOS's layout cannot show every field simultaneously. On the Lock Screen the
  countdown replaces the step/status message, and progress replaces supplementary
  text. The step remains in `critical_text` for the compact Dynamic Island; due
  and paused states show their message without a countdown. Tap the activity for
  the full dashboard. The title is static for an activity's lifetime.
- Countdown ticks on the device; identical reminder ticks do not send activity
  updates. Quiet updates may be delayed by iOS. Repeated starts while testing can
  exhaust Apple's push-to-start budget. Keep regular reminders enabled for actions.
- HA shutdown/unload retains the activity for restart recovery. To remove it,
  disable Live Activities while the integration is loaded, cancel/finish the
  bake, or end it in Companion. Failed clears retry when HA and the target are
  available; permanently removed devices may require dismissal on the phone.

Physical iPhone verification is still required on **staging**: start a bake,
confirm a step using a regular notification, adjust its schedule, pause/resume,
restart HA, and complete/cancel. Check the Lock Screen, compact/expanded Dynamic
Island, dashboard link, background/remote delivery, and an overnight renewal.
No real notifications or production HA access are used by the automated tests.

## Development

Target test baseline: Home Assistant **2026.10.4**, Python **3.14.2+**, and
`pytest-homeassistant-custom-component==0.13.375`. No runtime dependencies beyond HA.
The production HA version and phone destination are not available in this workspace;
select the phone during setup and verify your HA version before deployment.

On Linux with Python 3.14.2+:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest
ruff check .
ruff format --check .
mypy
# Or run all gates, stopping on the first failure:
python scripts/check.py
```

Windows contributors can run the real HA fixtures in an ephemeral Linux container:

```powershell
docker build -f Dockerfile.test -t bread-assistant-tests .
docker run --rm --network none -v "${PWD}:/work" bread-assistant-tests pytest
docker run --rm --network none -v "${PWD}:/work" bread-assistant-tests ruff check .
docker run --rm --network none -v "${PWD}:/work" bread-assistant-tests ruff format --check .
docker run --rm --network none -v "${PWD}:/work" bread-assistant-tests mypy
# Or run every gate in one container:
docker run --rm --network none -v "${PWD}:/work" bread-assistant-tests python scripts/check.py
```

Only mount this repository. No production config, secrets, ports, or Docker socket
are needed. The test image is development tooling, not a production service.

## Implementation progress

- P0: Specifications and empty repository inspected. Official HA lifecycle,
  actions, options, sensor, Store, UTC timer, and Companion APIs consulted.
  No production HA runtime/config volume is present. No configured phone is
  assumed. Isolated Linux fixtures selected; quality gates run as phases land.
- P1: Config/options flows, singleton behavior, lifecycle entry points and action
  schemas implemented. Two flow/API tests pass; lint passes. Runtime forwarding
  is exercised once the coordinator and platforms land in P3/P4.
- P2: Pure domain model, optional starter protocol/reference, both workflows,
  recipe graph validation, reference timeline and deterministic engine complete.
  Sixteen tests pass (including P1), Ruff clean; targeted domain typing checked.
- P3: Atomic HA Store schema v2, v1 migration, locked transactional mutations,
  bounded archives, one UTC callback and restart catch-up implemented. 23 tests
  pass, including Store/recovery/concurrent completion; domain typing passes.
- P4: One device, six sensors, seven controls and validated canonical actions
  implemented. All 26 tests pass with real HA setup/unload/reload, attributes,
  button dispatch and stale/invalid IDs; Ruff and domain typing pass.
- P5: Actionable iOS payloads with persisted random tokens, generation/lifecycle
  validation, rate-limited retries, exact ten-minute snooze and catch-up summaries
  implemented. 31 tests pass; lint/type gates pass. Physical iPhone validation
  remains manual because no phone or production HA connection is authorized.
- P6: Native-only dashboard includes both workflow starts, current guidance,
  Done/Snooze, lifecycle controls, all 21 timeline entries, local planned/actual
  times, progress, ingredients and safety. YAML, real HA templates and entity
  references tested (32 tests at phase completion); browser/device layout is manual.
- P7: Full workflow/restart, real HA simulated timers, shutdown-race and storage
  failure/version tests added. Documentation and final release checks complete;
  see the verification report for final results and explicit manual checks.

## Scope and operational limits

One active bake, one bundled recipe, the latest full bake and 50 archive summaries.
Cooking actions and biological readiness are always confirmed by a person. Bake
completion includes a final cooling check. Starter Manager itself is deliberately
absent; only the optional domain interface/reference is implemented.

Push delivery is rate limited and reserved durably before sending; a crash between
reservation and external delivery can postpone a reminder until its next repeat
interval. Physical iPhone delivery and remote connectivity have not been tested
here. Browser layout is checked in the isolated UI harness described above.
Real HA backend fixtures cover setup, reload, entities,
services, timers, Store and Companion event handling. Production HA has not been
contacted or changed. No compatibility beyond the stated test baseline is claimed.

Live Activities extension: 80 automated tests pass (46 existing, 34 added), with
Ruff lint/format and strict domain/Live Activity adapter typing. Coverage includes
creation, dynamic changes, pause/resume, completion/cancellation, restart and expiry,
independent/disabled channels, removed destinations, bounded retries, storage
failures and shutdown races. The phone-side behavior above remains a manual check.

Multilingual extension (15 November 2026): 107 automated tests pass, with Ruff
lint/format and strict mypy. Coverage includes English/Polish native assets,
placeholder/key completeness, fallback, automatic/manual selection, recipe and
notification content, Live Activity language updates, both dashboard languages,
and switching languages during an active bake without changing stored progress.
Browser and physical iPhone verification remain manual staging checks.

UI redesign (15 November 2026): 112 Python tests pass with Ruff lint/format and
strict mypy. Chromium checks pass for 234 viewport/theme/language/state combinations
plus service arguments, retry identities, focus, countdowns, connection recovery,
timeline expansion, narrow columns and timezone behavior. See
[UI validation](docs/ui-validation.md) for reproducible commands, screenshots and
the remaining physical iPhone/Safari and staging HA shell checks.
