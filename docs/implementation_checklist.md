# Implementation and verification report

Verified locally on 14 November 2026. The requested MVP is implemented; physical
device/browser staging checks and production deployment were not performed.

| Phase | Implementation | Verification / exceptions |
|---|---|---|
| P0 | Read both specifications, inspected repository, consulted official APIs, selected/pinned Linux HA fixtures and created developer tooling | Workspace initially contained only specifications. Production HA version/mount and iPhone destination unavailable; do not infer them from another project. Test baseline installed and inspected: HA 2026.10.4 / Python 3.14.2. |
| P1 | Config/options flow, singleton setup, lifecycle entry points, action schemas, English/Polish translations | Initial two tests and lint passed. Full runtime/platform lifecycle verification completed in P3/P4 when those modules existed. |
| P2 | Validated immutable recipe, pure UTC scheduler/domain, both starter workflows, optional starter reference and protocol | 16 tests at phase completion; lint and domain typing passed. Covers all 12 reference offsets, readiness, 17-minute delay, independent folds, midnight/DST. |
| P3 | Atomic HA Store v2, v1 migration, snapshot serialization, lock, transactional mutations, single timer, archives, events, catch-up | 23 tests at phase completion; Store roundtrip/migration/corruption, restart and concurrency verified. Strict domain typing passed. |
| P4 | Six sensors, seven buttons, stable device, validated canonical actions and service metadata | 26 tests at phase completion; real HA setup/unload/reload, state updates, IDs and action errors verified. Lint and domain typing passed. |
| P5 | iOS actionable payloads, persisted opaque token correlation, stale/duplicate rejection, ten-minute snooze, retry and catch-up | 31 tests at phase completion; phone simulated through real HA service/event APIs. Lint/type checks passed. Real iPhone, background delivery and remote connectivity validation deferred. |
| P6 | Native-only dashboard, both starts, current guidance, progress, controls, planned/due/actual timeline, recipe and safety | 32 tests including YAML/native types, real HA template rendering and matching registered entity references. Actual browser/mobile layout requires staging. |
| P7 | Whole bake scenarios, pending-write shutdown, stale timer guards, actual HA timer with simulated time, startup retries, safe unsupported versions; documentation and fail-fast checks | Final: **46 tests passed**, **91% statement coverage**, Ruff lint/format clean, mypy strict checks clean for five domain/serialization modules. No production changes. |

## Commands and final results

The development-only Docker image installs pinned HA fixture dependencies. Test
containers mount only the repository, expose no ports and run with network disabled.
They are removed automatically after the command; no production config or Docker
socket is mounted.

```powershell
docker build -f Dockerfile.test -t bread-assistant-tests .
docker run --rm --network none -v "${PWD}:/work" bread-assistant-tests python scripts/check.py --cov=custom_components.bread_assistant --cov-report=term-missing
```

`scripts/check.py` runs `ruff check .`, `ruff format --check .`, `mypy` and
`python -m pytest` in order and fails immediately on a failed gate. Final output:

```text
All checks passed!
27 files already formatted
Success: no issues found in 5 source files
46 passed
TOTAL: 91% statement coverage
```

Additionally imported the recipe loader and scheduler and created a bake using
standalone CPython 3.14.10 on Windows with no HA installation, confirming the
domain's independence from HA imports/runtime dependencies. HA adapter execution
was tested on Linux/Python 3.14.2, not Windows.

## Decisions and deviations

- User instructions override the plan's production-deployment task. No live HA
  instance was accessed or modified. Staging verification is represented by real
  isolated HA fixtures; physical phone and frontend smoke tests remain explicit
  manual tasks in [deployment](deployment.md).
- No production Compose/config file was available in this repository. Instructions
  explain how to identify the existing `/config` mount without inventing a path.
  Phone destinations are selected dynamically rather than committed to source.
- The unpublished repository has no confirmed documentation/issue URL. Manifest
  URLs are omitted rather than fabricated; README links local project docs.
- Prepared starter begins autolyse immediately, records feeding intentionally
  skipped, and retains the readiness checkpoint. Passing explicit readiness at
  start is valid only with that workflow. Original reference times stay unchanged.
- All timers are wall-clock. Pause freezes only reminders; it does not freeze
  fermentation or oven time. `adjust_step` requests an earliest reminder deadline;
  dependency scheduling still applies. Manual completion may be confirmed earlier
  for every stage once its prerequisites are met.
- The recipe uses 20 minutes as the uncovered reminder target while allowing actual
  removal at 15–20 minutes. The final manual cooling check completes the bake;
  the optional cooling-start technique item has no independent push.
- Archives are bounded to 50 and retain per-step status, planned, due and completion
  timestamps. Older summaries without step data still load. The latest full bake
  retains its snapshot; a history browser and import/export are outside this MVP.
- Push delivery cannot be transactional with Store. A crash after reservation but
  before send can postpone the next push until its repeat interval. This is an
  explicit durability/deduplication tradeoff; see [architecture](architecture.md).
- Only Home Assistant 2026.10.4 is verified. No claim of compatibility with every
  2026.x release is made. Starter Manager storage, monitoring and UI are excluded.

## Manual release checks remaining

- [ ] Confirm actual staging/production HA version and existing config mount.
- [ ] Select the user's actual mobile destination during setup.
- [ ] Test actual iPhone foreground/background/closed actionable notifications and
  existing remote connectivity.
- [ ] Inspect native dashboard on iPhone and desktop; adjust entity IDs if renamed
  or generated under another language.
- [ ] Complete the staging checklist in the deployment guide before the user
  independently chooses production installation and backup/rollback timing.
# Live Activities extension verification - 14 November 2026

The existing MVP was extended through its coordinator, Store and single UTC
callback. Regular actionable reminders, domain scheduling and dashboard controls
remain independent of the optional Live Activity channel.

- Verified the current [official Companion API](https://companion.home-assistant.io/docs/notifications/live-activities/)
  before implementation: `live_update`, stable `tag`, documented progress/timer
  fields, quiet updates, and `clear_notification` for ending.
- Defaults are disabled with no target. Setup/options include independent Live
  Activity controls and English/Polish labels. Runtime checks reject arbitrary
  services and tolerate unavailable mobile destinations.
- Covered creation, step and notification-action completion, schedule changes,
  due transitions, pause/resume, completion/cancellation, restart, overnight
  renewal, late service registration, target changes, disabled channels, durable
  failed cleanup, metadata failures and shutdown races.
- Baseline: 46 tests passed before changes. Final: **80 tests passed**, **92% total
  coverage**, **94% Live Activity adapter coverage**; Ruff lint/format and strict
  mypy for six source files passed. Test image: HA **2026.10.4**, Python **3.14.2**.
- Final command inside the existing `bread-assistant-tests` Linux image:
  `python scripts/check.py --cov=custom_components.bread_assistant --cov-report=term-missing`.
  The container mounted only this workspace and used `--network none`. All phone
  notification services were mocked. No production HA instance was contacted.
- Manual: [iPhone staging checklist and known limits](../README.md#ios-live-activities-optional).
  Physical display, push delivery, device-token handshake, background/remote
  operation, and eight-hour renewal continuity remain unverified on hardware.

