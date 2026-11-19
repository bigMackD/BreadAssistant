# Codex agent instructions - Bread Assistant

You are implementing a local-first Home Assistant custom integration named `bread_assistant`.

## Source of truth
- Read `IMPLEMENTATION_PLAN.md` before editing code.
- Verify version-sensitive HA APIs against official HA documentation and the installed HA Core version.
- First recipe: https://justynadragan.pl/2020/08/podstawowy-chleb-pszenny-na-zakwasie.html

## Execution contract
- Implement the actual end-to-end MVP, not only a design or scaffold.
- Follow phases P0–P7 and their acceptance criteria in order.
- Prefer simple, maintainable HA-native Python architecture over extra services or dependencies.
- Pure domain scheduling logic should be independently unit-testable.
- Strictly distinguish planned time, actual time, and reminder snooze time.
- Never auto-assert that a starter or dough is ready based only on elapsed time.
- Keep all timestamps timezone-aware (UTC in storage, HA local timezone in UI).
- Persist state with HA Store and restore timers/event listeners without duplication.
- Never trust stale mobile notification actions; verify bake, step, generation, and lifecycle.
- Validate HA service action arguments; keep callbacks and listeners lifecycle-safe.
- Use supported built-in Lovelace cards for the MVP dashboard.
- Attribute the original recipe and paraphrase instructions; do not scrape or bulk-copy content.
- Do not alter the live HA instance, Docker Compose configuration, user secrets, or network settings unless explicitly authorized.

## Quality gates
- After every phase, run tests and lint, address failures, and record results.
- Include restart, overdue, concurrency, stale push action, timezone, and DST tests.
- Deliver tested integration files, a usable dashboard, setup instructions, and a final implementation report.
- Clearly report remaining limitations rather than claiming untested features work.
