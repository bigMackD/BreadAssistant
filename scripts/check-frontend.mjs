/** Isolated browser checks with real sensor snapshots. Never connects to HA.
 * node scripts/check-frontend.mjs [path/to/playwright-core]
 * Generate fixtures first: python -m scripts.frontend_fixtures
 */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve, extname, sep } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require(process.argv[2] || "../.tools/frontend/node_modules/playwright");
const base = resolve("custom_components/bread_assistant/frontend");
const output = resolve("test-results/frontend");
const fixtures = JSON.parse(await readFile(resolve(output, "fixtures.json"), "utf8"));
const html = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{margin:0;background:var(--primary-background-color);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif} .unrelated{position:fixed;left:-1000px}</style></head>
<body><button class="unrelated">Other dashboard</button><main></main>
<script type="module">
import { BreadAssistantCard } from '/bread-assistant-card.js';
import { strings } from '/strings.js';
window.strings = strings;
window.show = (states, language, connected = true, config = {}) => {
  const card = new BreadAssistantCard(); card.setConfig(config);
  window.calls = []; window.fail = false; window.pending = false;
  window.hass = { states: structuredClone(states), language,
    config: {time_zone:'Europe/Warsaw'}, connection: {connected},
    callService: async (domain, service, data) => {
      window.calls.push({domain,service,data:structuredClone(data)});
      if (window.fail) throw new Error(language === 'pl' ? 'Błąd testowy' : 'Test failure');
      if (window.pending) await new Promise(resolve => { window.finish = resolve; });
    }
  };
  card.hass = window.hass;
  document.querySelector('main').replaceChildren(card); window.card = card;
};
window.ready = true;
</script></body></html>`;
const server = createServer(async (request, response) => {
  try {
    if (request.url === "/") {
      response.setHeader("Content-Type", "text/html"); response.end(html); return;
    }
    const file = resolve(base, `.${new URL(request.url, "http://localhost").pathname}`);
    if (!file.startsWith(base + sep) || extname(file) !== ".js") {
      response.writeHead(404); response.end(); return;
    }
    response.setHeader("Content-Type", "application/javascript");
    response.end(await readFile(file));
  } catch { response.writeHead(404); response.end(); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const browser = await chromium.launch({ headless: true });
const errors = [];
const themes = {
  light: {
    "primary-color": "#03a9f4", "primary-background-color": "#fafafa", "secondary-background-color": "#f0f0f0",
    "card-background-color": "#ffffff", "primary-text-color": "#212121", "secondary-text-color": "#606060",
    "divider-color": "rgba(0,0,0,.12)", "warning-color": "#ff9800", "error-color": "#db4437", "success-color": "#168544",
  },
  dark: {
    "primary-color": "#03a9f4", "primary-background-color": "#111111", "secondary-background-color": "#202020",
    "card-background-color": "#1c1c1c", "primary-text-color": "#e1e1e1", "secondary-text-color": "#b5b5b5",
    "divider-color": "rgba(255,255,255,.12)", "warning-color": "#ff9800", "error-color": "#ff736a", "success-color": "#4caf50",
  },
  maciek: fixtures.reference_theme,
};
let count = 0;
let instructionCount = 0;
try {
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  page.on("pageerror", error => errors.push(error.message));
  await page.clock.install({ time: new Date(fixtures.now) });
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.waitForFunction(() => window.ready);
  const card = page.locator("bread-assistant-card");
  for (const [size, width, height] of [["mobile",402,874], ["tablet",834,1194], ["desktop",1440,1000]]) {
    await page.setViewportSize({ width, height });
    for (const [theme, variables] of Object.entries(themes)) {
      await page.emulateMedia({ colorScheme: theme === "light" ? "light" : "dark" });
      await page.evaluate(vars => {
        document.documentElement.removeAttribute("style");
        for (const [key, value] of Object.entries(vars)) document.documentElement.style.setProperty(`--${key}`, value);
      }, variables);
      for (const [language, scenarios] of Object.entries(fixtures.scenarios)) {
        for (const [scenario, states] of Object.entries(scenarios)) {
          await page.evaluate(({states, language, scenario}) => window.show(states, language, scenario !== "disconnected"), { states, language, scenario });
          await card.locator("h1").waitFor();
          assert.equal(await card.locator("h1").innerText(), "Bread Assistant");
          const layout = await card.evaluate(element => {
            const root = element.shadowRoot;
            const overflow = [...root.querySelectorAll("*")].filter(item => {
              const rect = item.getBoundingClientRect();
              return rect.width && rect.height && !item.classList.contains("sr-only") &&
                (rect.right > innerWidth + 1 || rect.left < -1);
            }).map(item => item.className || item.tagName);
            return { overflow, columns: root.querySelector(".layout") ? getComputedStyle(root.querySelector(".layout")).gridTemplateColumns.split(" ").length : null };
          });
          assert.deepEqual(layout.overflow, [], `${size}/${theme}/${language}/${scenario}: overflow`);
          if (layout.columns) assert.equal(layout.columns, size === "mobile" ? 1 : 2);
          if (scenario === "unavailable") {
            assert.equal(await card.locator("button[data-action]").count(), 0);
          } else {
            for (const label of ["ingredients", "instructions", "diagnostics"]) {
              await card.locator(`[data-detail="${label}"] > summary`).click();
              assert.equal(await card.locator(`[data-detail="${label}"]`).getAttribute("open"), "");
            }
            if (scenario === "active") assert.equal(await card.locator('[data-action="complete"]').isDisabled(), true);
            if (["due", "overdue", "prepared", "snoozed"].includes(scenario)) assert.equal(await card.locator('[data-action="complete"]').isEnabled(), true);
            if (scenario === "paused") {
              assert.equal(await card.locator('[data-action="complete"]').count(), 0);
              assert.equal(await card.locator('[data-countdown]').innerText(), language === "pl" ? "Przypomnienia wstrzymane" : "Reminders paused");
            }
            if (scenario === "disconnected") assert.equal(await card.locator('button[data-action]:enabled:not([data-action="timeline"])').count(), 0);
            assert.equal(await card.locator(".step").count(), states["sensor.bread_assistant_current_step"].attributes.timeline.length);
            if (["due", "overdue", "snoozed"].includes(scenario)) {
              const fullInstructions = states["sensor.bread_assistant_current_step"].attributes.instructions;
              await card.locator('[data-detail="current-instructions"] > summary').click();
              assert.equal(await card.locator('[data-detail="current-instructions"] .current-instructions-copy').innerText(), fullInstructions);
              assert.match(fullInstructions, /40 g/);
              assert.match(fullInstructions, /80 g/);
              assert.match(fullInstructions, language === "pl" ? /dwukrotnie/ : /doubled/);
              assert.match(fullInstructions, language === "pl" ? /się zapadł/ : /collapsed/);
              assert.match(await card.locator(".confirmation-hint").innerText(), language === "pl" ? /po dokarmieniu/ : /after feeding/);
              assert.equal(await card.locator('[data-action="complete"]').isEnabled(), true);
              const overflow = await card.evaluate(element => element.scrollWidth > innerWidth);
              assert.equal(overflow, false, `${size}/${theme}/${language}: expanded instructions overflow`);
              if (scenario === "due" && theme === "maciek" && language === "pl") {
                await page.screenshot({path:resolve(output, `${size}-feeding-full-instructions.png`), fullPage:true, animations:"disabled"});
              }
            }
          }
          // Capture representative states, with folded disclosures for the overview.
          if ((scenario === "active" && (theme === "maciek" || theme === "light")) ||
              (size === "mobile" && theme === "maciek" && language === "pl" && ["idle","paused","completed","error","overdue"].includes(scenario))) {
            await card.locator("details[open]").evaluateAll(items => items.forEach(item => { item.open = false; }));
            await page.screenshot({ path: resolve(output, `${size}-${theme}-${language}-${scenario}.png`), fullPage: true, animations: "disabled" });
          }
          count++;
        }
      }
    }
  }
  // Every stage's source passage renders in full, separately from its summary and
  // confirmation guidance, including long multi-paragraph and multi-method text.
  for (const [size, width, height] of [["mobile",402,874], ["tablet",834,1194], ["desktop",1440,1000]]) {
    await page.setViewportSize({width,height});
    for (const [theme, variables] of Object.entries(themes)) {
      await page.evaluate(vars => {
        document.documentElement.removeAttribute("style");
        for (const [key, value] of Object.entries(vars)) document.documentElement.style.setProperty(`--${key}`, value);
      }, variables);
      for (const [language, stages] of Object.entries(fixtures.stage_scenarios)) {
        for (const [stepId, states] of Object.entries(stages)) {
          await page.evaluate(({states,language}) => window.show(states,language), {states,language});
          const attrs = states["sensor.bread_assistant_current_step"].attributes;
          assert.equal(attrs.step_id, stepId);
          assert.equal(await card.locator(".stage-copy").innerText(), attrs.instructions_summary);
          const details = card.locator('[data-detail="current-instructions"]');
          await details.locator("summary").click();
          assert.equal(await details.locator(".current-instructions-copy").innerText(), attrs.instructions);
          assert.equal(await details.locator(".eyebrow").textContent(), attrs.instructions_attribution);
          assert.match(await card.locator(".confirmation-hint").innerText(), new RegExp(language === "pl" ? "Kiedy potwierdzić" : "When to confirm"));
          assert.equal(await details.locator("a").getAttribute("href"), states["sensor.bread_assistant_status"].attributes.recipe_url);
          assert.equal(await card.evaluate(element => element.scrollWidth <= innerWidth), true, `${size}/${theme}/${language}/${stepId}: instruction overflow`);
          const due = await page.evaluate(value => Date.parse(value) <= Date.now(), attrs.due_at);
          assert.equal(await card.locator('[data-action="complete"]').isEnabled(), due);
          if (size === "mobile" && theme === "maciek" && language === "pl" && ["preshape","dough_ready","bake_start","cooling_check"].includes(stepId)) {
            await page.screenshot({path:resolve(output, `${size}-${stepId}-full-instructions.png`), fullPage:true, animations:"disabled"});
          }
          instructionCount++;
        }
      }
    }
  }
  // Check dictionaries independently of visual snapshots.
  assert.equal(await page.evaluate(() => JSON.stringify(Object.keys(strings.en).sort()) === JSON.stringify(Object.keys(strings.pl).sort())), true);
  await page.setViewportSize({ width: 402, height: 874 });
  const show = async (name, language = "en") => page.evaluate(({states, language}) => window.show(states, language), { states: fixtures.scenarios[language][name], language });
  const click = (action) => card.locator(`[data-action="${action}"]`).first().click();
  await show("cold_proof");
  assert.equal(await card.locator(".step:visible").count(), 5);
  assert.equal(await card.locator('.step[aria-current="step"]:visible').count(), 1);
  await click("timeline");
  assert.equal(await card.locator(".step:visible").count(), 21);
  await card.locator('[data-detail="step-0"] > summary').click();
  assert.match(await card.locator('[data-detail="step-0"]').innerText(), /Plan/);
  await click("timeline");
  assert.equal(await card.locator(".step:visible").count(), 5);
  await show("idle"); await click("feed");
  assert.deepEqual(await page.evaluate(() => calls[0]), {domain:"bread_assistant", service:"start_bake", data:{starter_workflow:"feed"}});
  await show("idle"); await click("prepared");
  assert.equal(await page.evaluate(() => calls[0].data.starter_workflow), "prepared");
  await show("due"); await click("complete");
  assert.deepEqual(await page.evaluate(() => calls[0]), {
    domain:"bread_assistant", service:"complete_step", data:{
      bake_id:fixtures.scenarios.en.due["sensor.bread_assistant_status"].attributes.bake_id, step_id:"feed_starter",
    },
  });
  await show("due"); await click("snooze");
  assert.equal(await page.evaluate(() => calls[0].data.minutes), 10);
  assert.equal(await page.evaluate(() => calls[0].service), "snooze_step");
  await show("active"); await click("pause");
  assert.equal(await page.evaluate(() => calls[0].service), "pause_bake");
  await show("paused"); await click("resume");
  assert.equal(await page.evaluate(() => calls[0].service), "resume_bake");
  await show("active");
  page.once("dialog", dialog => dialog.dismiss()); await click("cancel");
  assert.equal(await page.evaluate(() => calls.length), 0);
  page.once("dialog", dialog => dialog.accept()); await click("cancel");
  assert.equal(await page.evaluate(() => calls[0].service), "cancel_bake");
  // A slow service cannot be submitted twice.
  await show("due"); await page.evaluate(() => { window.pending = true; }); await click("complete");
  assert.equal(await card.locator('[data-action="complete"]').isDisabled(), true);
  assert.equal(await page.evaluate(() => calls.length), 1);
  await page.evaluate(() => window.finish());
  await card.locator('[data-action="complete"]:enabled').waitFor();
  assert.equal(await card.evaluate(element => element.shadowRoot.activeElement?.dataset.action), "complete");
  // Retry uses the captured identity, including after another viewer changes the bake.
  await show("due", "pl"); await page.evaluate(() => { window.fail = true; }); await click("complete");
  assert.match(await card.locator('[data-action-error]').innerText(), /Błąd testowy/);
  await page.evaluate(() => {
    window.hass = {...hass, states:structuredClone(hass.states)};
    hass.states["sensor.bread_assistant_current_step"].attributes.step_id = "other-step";
    card.hass = hass; window.fail = false;
  });
  await click("retry");
  assert.equal(await page.evaluate(() => calls[1].data.step_id), "feed_starter");
  // Disclosures, keyboard focus and the DOM survive a countdown tick.
  await show("active");
  await card.locator('[data-detail="ingredients"] > summary').click();
  await page.evaluate(() => { window.originalTimer = card.shadowRoot.querySelector('[data-countdown]'); });
  const before = await card.locator('[data-countdown]').innerText();
  await page.clock.runFor(2000);
  assert.notEqual(await card.locator('[data-countdown]').innerText(), before);
  assert.equal(await page.evaluate(() => window.originalTimer === card.shadowRoot.querySelector('[data-countdown]')), true);
  assert.equal(await card.locator('[data-detail="ingredients"]').getAttribute("open"), "");
  await page.evaluate(() => {
    hass = {...hass, states:structuredClone(hass.states)};
    hass.states["sensor.bread_assistant_progress"].state = "25"; card.hass = hass;
  });
  assert.equal(await card.locator('[data-detail="ingredients"]').getAttribute("open"), "");
  assert.equal(await card.evaluate(element => element.shadowRoot.activeElement?.parentElement?.dataset.detail), "ingredients");
  assert.equal(await card.locator('[role="progressbar"]').getAttribute("aria-valuenow"), "25");
  // Shared connection objects can mutate without a new hass setter call.
  await page.evaluate(() => { hass.connection.connected = false; }); await page.clock.runFor(1000);
  assert.equal(await card.locator('button[data-action]:enabled:not([data-action="timeline"])').count(), 0);
  await page.evaluate(() => { hass.connection.connected = true; }); await page.clock.runFor(1000);
  assert.equal(await card.locator('[data-action="pause"]').isEnabled(), true);
  // At the deadline the primary action becomes available without recreating the card.
  await page.evaluate(states => {
    const imminent = structuredClone(states);
    imminent["sensor.bread_assistant_current_step"].attributes.due_at = new Date(Date.now() + 1000).toISOString();
    window.show(imminent, "en");
  }, fixtures.scenarios.en.active);
  assert.equal(await card.locator('[data-action="complete"]').isDisabled(), true);
  await page.clock.runFor(2000);
  assert.equal(await card.locator('[data-action="complete"]').isEnabled(), true);
  assert.equal(await page.evaluate(() => calls.length), 0); // Readiness is never inferred.
  // 12h/24h and DST use HA's configured zone, irrespective of the browser's zone.
  await page.evaluate(states => {
    const twelve = structuredClone(states);
    twelve["sensor.bread_assistant_status"].attributes.time_format = "12h";
    window.show(twelve, "en");
  }, fixtures.scenarios.en.active);
  assert.match(await card.locator(".due-time").first().innerText(), /PM/);
  assert.equal(await card.evaluate(element => element._date("2026-03-29T00:30:00Z")).then(text => text.includes("01:30")), true);
  assert.equal(await card.evaluate(element => element._date("2026-03-29T01:30:00Z")).then(text => text.includes("03:30")), true);
  // A narrow dashboard column, unsupported language, missing sensors and partial data stay usable.
  await page.setViewportSize({width:320,height:800});
  await page.evaluate(states => {
    const partial = structuredClone(states);
    partial["sensor.bread_assistant_status"].attributes.language = "de";
    partial["sensor.bread_assistant_status"].attributes.recipe_title = "LongRecipeTitle".repeat(10);
    partial["sensor.bread_assistant_status"].attributes.last_error = "LongError".repeat(50);
    partial["sensor.bread_assistant_progress"].state = "unavailable";
    window.show(partial, "de");
  }, fixtures.scenarios.en.active);
  assert.equal(await card.locator('[role="progressbar"]').getAttribute("aria-valuenow"), "0");
  assert.equal(await card.evaluate(element => element.scrollWidth <= innerWidth), true);
  await page.evaluate(states => {
    const partial = structuredClone(states); delete partial["sensor.bread_assistant_current_step"];
    window.show(partial, "en");
  }, fixtures.scenarios.en.active);
  assert.equal(await card.locator('[data-action="complete"]').isDisabled(), true);
  assert.equal(await card.locator('[data-countdown]').innerText(), "—");
  // Configuration rejects invalid IDs before rendering.
  assert.equal(await page.evaluate(() => {
    try { card.setConfig({entity_prefix:"sensor.bad"}); return false; } catch { return true; }
  }), true);
  await page.setViewportSize({width:402,height:874});
  // Sensor IDs can be overridden individually after registry renames.
  await page.evaluate(states => {
    const renamed = structuredClone(states); renamed["sensor.renamed_status"] = renamed["sensor.bread_assistant_status"];
    delete renamed["sensor.bread_assistant_status"];
    window.show(renamed, "en", true, {entities:{status:"sensor.renamed_status"}});
  }, fixtures.scenarios.en.idle);
  assert.equal(await card.locator('[data-action="feed"]').isEnabled(), true);
  // Theme changes propagate through CSS without rebuilding the card.
  const colors = await card.evaluate(element => {
    const hero = element.shadowRoot.querySelector("ha-card"); const before = getComputedStyle(hero).backgroundColor;
    element.style.setProperty("--ha-card-background", "rgb(12, 34, 56)");
    return {before, after:getComputedStyle(hero).backgroundColor};
  });
  assert.notEqual(colors.before, colors.after); assert.equal(colors.after, "rgb(12, 34, 56)");
  await page.emulateMedia({ reducedMotion: "reduce" });
  assert.equal(await card.locator("button").first().evaluate(el => getComputedStyle(el).transitionDuration), "0s");
  assert.equal(await page.locator(".unrelated").evaluate(el => getComputedStyle(el).minHeight), "0px");
  // Untrusted recipe/error content stays text, and unsafe source protocols are rejected.
  await page.evaluate(states => {
    const bad = structuredClone(states);
    Object.assign(bad["sensor.bread_assistant_status"].attributes, {
      recipe_title:'<img src=x onerror="window.injected=true">', recipe_url:"javascript:alert(1)", last_error:"<script>bad()</script>",
    }); window.show(bad, "en");
  }, fixtures.scenarios.en.active);
  assert.equal(await card.locator("img, script, a[href^='javascript:']").count(), 0);
  assert.match(await card.locator(".recipe-title").innerText(), /<img/);
  // Removing the card clears its timer; reconnecting starts just one timer.
  assert.equal(await page.evaluate(() => {
    const current = window.card; current.remove(); const cleared = current._interval === undefined;
    document.querySelector("main").append(current); const timer = current._interval;
    current.connectedCallback(); return cleared && timer === current._interval;
  }), true);
  assert.deepEqual(errors, []);
  await mkdir(output, {recursive:true});
  const report = { combinations:count, instruction_combinations:instructionCount, widths:[402,834,1440], themes:Object.keys(themes), languages:["en","pl"], scenarios:Object.keys(fixtures.scenarios.en), stages:Object.keys(fixtures.stage_scenarios.en), browser:browser.version(), errors };
  await writeFile(resolve(output, "report.json"), JSON.stringify(report, null, 2));
  console.log(`${count} lifecycle combinations and ${instructionCount} full-instruction combinations passed; actions, retry identities, countdown, disconnect, scoped themes and reduced motion passed.`);
} finally {
  await browser.close(); await new Promise(resolve => server.close(resolve));
}
