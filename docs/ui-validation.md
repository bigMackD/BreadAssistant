# Bread Assistant UI validation

The redesign is implemented as a bundled Lovelace custom element, with no build
step or optional frontend dependencies. Baking actions, sensors, notifications,
storage and scheduling retain their existing contracts. The original native-only
dashboard is preserved in `dashboards/bread_assistant_native.yaml`.

## Automated coverage

The browser harness renders the actual card ES modules with snapshots produced by
the real `BreadSensor` adapter and deterministic domain scenarios. It supplies a
mock `hass` object for service calls, and runs entirely on a temporary loopback
server. It does not connect to a running HA instance or send notifications.

| Dimension | Coverage |
| --- | --- |
| Viewports | 402 × 874 (iPhone 16 Pro CSS viewport), 834 × 1194, 1440 × 1000 |
| Themes | HA-style light defaults, dark defaults, exact supplied Maciek iOS dark tokens |
| Languages | English and Polish, including localized recipe/safety content |
| States | Idle, active/waiting, due, overdue, snoozed, paused, completed, canceled, prepared starter, cold proof, delivery error, unavailable, disconnected |
| Layout result | 234 combinations; no horizontal overflow; expected one/two-column layouts |

Additional browser assertions cover:

- Both starter workflows, Done, ten-minute Snooze, Pause, Resume, confirmed Cancel
  and dismissed Cancel, including exact service arguments and captured bake/step IDs.
- In-flight action locking, failure display and retries retaining the original step
  after an intervening state update.
- Local countdown updates and deadline crossing without automatic completion or
  HA writes; timer cleanup on removal and a single interval after reconnecting.
- Connection loss and recovery, including mutation of the shared connection object.
- Nearby/full timeline switching and planned/actual timestamps; expanding recipe,
  instruction and diagnostic groups; preserving expanded details and keyboard focus.
- Individual renamed sensor overrides, invalid configuration, missing current-step
  sensor, unavailable progress, unsupported-language fallback and a 320px column
  containing long recipe titles and error text.
- 12-hour display, HA system timezone and the spring DST transition in Warsaw.
- Dynamic HA theme inheritance, reduced-motion settings and CSS isolation from an
  unrelated dashboard button. Escaped recipe/error text and safe source URL schemes.

Real HA tests cover HTTP asset serving, path traversal rejection, headless setup,
HTTP without frontend, automatic module registration and config-entry reload.
The frontend lifecycle test supplies an empty static asset directory because the
backend test image omits HA's browser asset wheel; the module loader runs normally.
All **112 Python tests** pass, including the existing integration regression suite.
Ruff lint/format and strict mypy pass. Existing native dashboard templates still
render in both languages. The browser matrix and additional assertions all pass.

## Reproduce

Run the backend checks in the existing pinned Linux test environment:

```powershell
docker run --rm --network none -v "${PWD}:/work" bread-assistant-tests python scripts/check.py
docker run --rm --network none -v "${PWD}:/work" bread-assistant-tests python -m scripts.frontend_fixtures
```

For browser checks, use Node 20+ and Playwright (test tooling only). If unavailable,
install it into the ignored tools directory and install its Chromium browser:

```powershell
npm install --prefix .tools/frontend playwright@1.56.1
.tools/frontend/node_modules/.bin/playwright install chromium
node scripts/check-frontend.mjs
```

An existing Playwright or playwright-core installation can instead be supplied as
the first script argument. The validated run used Chromium 141.0.7390.37.
Screenshots, sensor fixtures and `report.json` are written under the ignored
`test-results/frontend/` directory. No application dependencies are installed by
the card, and no production deployment is performed.

## Manual verification boundary

Chromium viewport checks are not physical iPhone/Safari or Companion testing. The
harness does not render HA's navigation shell, native `ha-card` internals or MDI
icons. Review the dashboard in staging HA on actual devices, especially safe-area
insets, larger iOS text sizes, VoiceOver navigation and Companion reconnect/cache
behavior. Test actual notification delivery separately using the existing staging
checklist. The provided personal theme defines only dark mode; light-mode checks
use default light tokens rather than inventing a personal light theme.

The HA frontend APIs were checked against installed Core 2026.10.4 and the official
[custom-card contract](https://contributors.home-assistant.io/frontend/custom-ui/card/)
and [async static-path guidance](https://contributors.home-assistant.io/blog/2024/06/18/async_register_static_paths/).
