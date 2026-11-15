import { styles } from "./styles.js";
import { strings } from "./strings.js";

const SENSOR_KEYS = ["status", "current_step", "next_step", "next_due", "progress", "overdue_count"];
const VALID_STATES = new Set(["idle", "active", "paused", "completed", "canceled"]);
const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[char]);
const copy = (value) => escapeHTML(value).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
const timestamp = (value) => value ? Date.parse(value) : NaN;
const finished = (step) => ["done", "skipped"].includes(step.state);
const icon = (name) => `<ha-icon icon="mdi:${name}" aria-hidden="true"></ha-icon>`;

export class BreadAssistantCard extends HTMLElement {
  static getStubConfig() { return { entity_prefix: "bread_assistant" }; }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._busy = false;
    this._error = "";
    this.shadowRoot.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (button && !button.disabled) this._act(button.dataset.action);
    });
  }

  setConfig(config) {
    const prefix = config.entity_prefix ?? "bread_assistant";
    if (typeof prefix !== "string" || !/^[a-z0-9_]+$/.test(prefix)) {
      throw new Error("entity_prefix must be an entity object ID, e.g. kitchen_bread_assistant");
    }
    if (config.entities && (typeof config.entities !== "object" || Array.isArray(config.entities))) {
      throw new Error("entities must map sensor keys to entity IDs");
    }
    this._entities = Object.fromEntries(SENSOR_KEYS.map((key) => {
      const id = config.entities?.[key] ?? `sensor.${prefix}_${key}`;
      if (typeof id !== "string" || !/^sensor\.[a-z0-9_]+$/.test(id)) {
        throw new Error(`Invalid sensor entity for ${key}`);
      }
      return [key, id];
    }));
    this._render();
  }

  set hass(hass) {
    const old = this._hass;
    this._hass = hass;
    if (!this._entities) return;
    // Ignore unrelated entity churn; the only per-second work is local text updates.
    if (!old || SENSOR_KEYS.some((key) => old.states[this._entities[key]] !== hass.states[this._entities[key]]) ||
        old.connection?.connected !== hass.connection?.connected || old.language !== hass.language ||
        this._connected !== this._isConnected()) {
      this._render();
    }
  }

  getCardSize() { return 18; }
  getGridOptions() { return { columns: 12, min_columns: 6 }; }

  connectedCallback() {
    this._render();
    if (!this._interval) this._interval = setInterval(() => this._tick(), 1000);
  }

  disconnectedCallback() {
    clearInterval(this._interval);
    this._interval = undefined;
  }

  _isConnected() { return this._hass?.connection?.connected !== false; }
  _state(key) { return this._hass?.states[this._entities?.[key]]; }
  _text(key) { return this._strings[key] ?? strings.en[key] ?? key; }

  _date(value) {
    if (!Number.isFinite(timestamp(value))) return "—";
    const timeZone = this._hass?.config?.time_zone || "UTC";
    const options = {
      timeZone, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
      hour12: this._attrs.time_format === "12h", timeZoneName: "short",
    };
    try { return new Intl.DateTimeFormat(this._language, options).format(new Date(value)); }
    catch { return new Intl.DateTimeFormat("en", { ...options, timeZone: "UTC" }).format(new Date(value)); }
  }

  _button(action, label, primary = false, disabled = false) {
    return `<button type="button" data-action="${action}" class="${primary ? "primary" : "secondary"}"
      ${disabled || this._busy || !this._connected ? "disabled" : ""}>${escapeHTML(this._text(label))}</button>`;
  }

  _disclosure(id, label, glyph, body) {
    return `<div class="card"><details class="group" data-detail="${id}">
      <summary>${icon(glyph)}${escapeHTML(this._text(label))}</summary>
      <div class="detail-body">${body}</div></details></div>`;
  }

  _render() {
    if (!this._hass || !this._entities) return;
    const root = this.shadowRoot;
    const open = new Set([...root.querySelectorAll("details[open]")].map((detail) => detail.dataset.detail));
    const focus = root.activeElement?.dataset.action || this._focusAction;
    const focusDetail = root.activeElement?.closest("details")?.dataset.detail;
    this._connected = this._isConnected();
    const status = this._state("status");
    this._attrs = status?.attributes ?? {};
    const language = (this._attrs.language || this._hass.language || "en").toLowerCase().split(/[-_]/)[0];
    this._language = strings[language] ? language : "en";
    this._strings = strings[this._language] ?? strings.en;
    this._ui = this._attrs.ui ?? {};
    this._status = status?.state;
    const current = this._state("current_step");
    this._step = current?.attributes ?? {};
    this._timeline = Array.isArray(this._step.timeline) ? this._step.timeline : [];
    this._running = ["active", "paused"].includes(this._status);
    this._view = { bake_id: this._attrs.bake_id, step_id: this._step.step_id };
    const rawProgress = Number(this._state("progress")?.state);
    this._progress = Number.isFinite(rawProgress) ? Math.min(100, Math.max(0, rawProgress)) : 0;
    const available = VALID_STATES.has(this._status);
    this._available = available;
    const warning = this._attrs.last_error || this._attrs.live_activity_error;
    root.innerHTML = `<style>${styles}</style><div class="shell" lang="${escapeHTML(this._language)}">
      <header><div class="brand-icon">${icon("bread-slice-outline")}</div>
        <div><p class="eyebrow">${escapeHTML(this._text("kitchen"))}</p><h1>${escapeHTML(this._text("title"))}</h1></div>
        ${available ? `<span class="badge status">${escapeHTML(this._attrs.status_label || this._text(this._status))}</span>` : ""}
      </header>
      <div data-connection>${!this._connected ? this._notice("disconnected", "", true) : ""}</div>
      <div data-action-error role="alert">${this._error ? this._notice("action_error", this._error, true, true) : ""}</div>
      ${!available ? this._notice("unavailable", this._text("unavailable_body"), true) : `
        <div class="layout">
          <div class="column">
            ${warning ? this._notice("delivery_error", warning, true) : ""}
            ${this._status === "paused" ? this._notice("paused_title", this._ui.paused || this._text("paused_timer")) : ""}
            ${this._running ? this._hero(current) : this._empty()}
            ${this._timeline.length ? this._stats() : ""}
            ${this._running ? `<div class="controls">
              <button type="button" data-action="${this._status === "paused" ? "resume" : "pause"}" ${this._busy || !this._connected ? "disabled" : ""}>${escapeHTML(this._text(this._status === "paused" ? "resume" : "pause"))}</button>
              <button type="button" class="danger" data-action="cancel" ${this._busy || !this._connected ? "disabled" : ""}>${escapeHTML(this._text("cancel"))}</button>
            </div>` : ""}
            ${this._recipe()}
            ${this._diagnostics()}
          </div>
          <div class="column">${this._timelineCard()}</div>
        </div>`}
    </div>`;
    root.querySelectorAll("details").forEach((detail) => { detail.open = open.has(detail.dataset.detail); });
    this._tick();
    if (focus && !this._busy) {
      const target = root.querySelector(`button[data-action="${focus}"]:not(:disabled)`) || root.querySelector(".stage");
      target?.focus({ preventScroll: true });
    }
    else if (focusDetail) [...root.querySelectorAll("details")].find((detail) => detail.dataset.detail === focusDetail)
      ?.querySelector("summary")?.focus({ preventScroll: true });
  }

  _notice(title, body, error = false, retry = false) {
    return `<div class="card notice ${error ? "error" : ""}" ${retry ? "" : 'role="status"'}>
      <h3>${escapeHTML(this._text(title))}</h3>${body ? `<p>${copy(body)}</p>` : ""}
      ${retry ? this._button("retry", "retry") : ""}</div>`;
  }

  _hero(current) {
    const circumference = 2 * Math.PI * 54;
    const instructions = this._step.instructions || this._ui.start_hint || "";
    const concise = instructions.match(/^.*?[.!?](?:\s|$)/)?.[0] || instructions;
    const title = current && !["unknown", "unavailable"].includes(current.state) ? current.state : this._ui.no_task;
    return `<ha-card class="hero">
      <div class="hero-top">
        <div class="ring" role="progressbar" aria-label="${escapeHTML(this._text("progress"))}"
          aria-valuemin="0" aria-valuemax="100" aria-valuenow="${this._progress}">
          <svg viewBox="0 0 120 120" aria-hidden="true"><circle class="ring-track" cx="60" cy="60" r="54"/>
            <circle class="ring-progress" cx="60" cy="60" r="54" stroke-dasharray="${circumference * this._progress / 100} ${circumference}"/>
          </svg><div class="ring-value"><span class="percent">${new Intl.NumberFormat(this._language, { maximumFractionDigits: 0 }).format(this._progress)}%</span>
            <span class="ring-label">${escapeHTML(this._text("progress"))}</span></div>
        </div>
        <div class="hero-title"><p class="eyebrow">${escapeHTML(this._text(this._status === "paused" ? "paused" : "active"))}</p>
          <p class="recipe-title">${escapeHTML(this._attrs.recipe_title)}</p></div>
      </div>
      <div class="timer-block"><p class="eyebrow" data-countdown-label></p>
        <div class="countdown" data-countdown role="timer" aria-live="off"></div>
        <p class="due-time">${escapeHTML(this._text("due"))} · ${escapeHTML(this._date(this._step.due_at))}</p>
        ${this._step.snoozed_until ? `<p class="footnote">${escapeHTML(this._text("snoozed"))} ${escapeHTML(this._date(this._step.snoozed_until))}</p>` : ""}
      </div>
      <p class="eyebrow">${escapeHTML(this._text("current"))}</p><h2 class="stage" tabindex="-1">${escapeHTML(title)}</h2>
      <p class="stage-copy">${copy(concise)}</p>
      <div class="actions">${this._status === "paused" ? this._button("resume", "resume", true) :
        `${this._button("complete", "done", true, true)}${this._button("snooze", "snooze", false, true)}`}</div>
      <p class="footnote" data-waiting></p><p class="footnote">${copy(this._ui.confirm || this._text("check"))}</p>
      <span class="sr-only" role="status">${this._busy ? escapeHTML(this._text("working")) : ""}</span>
    </ha-card>`;
  }

  _empty() {
    const state = ["completed", "canceled"].includes(this._status) ? this._status : "idle";
    return `<ha-card class="empty"><div class="brand-icon">${icon(state === "completed" ? "check-all" : "bread-slice-outline")}</div>
      <h2>${escapeHTML(this._text(`${state}_title`))}</h2><p class="muted">${escapeHTML(this._text(`${state}_body`))}</p>
      <p class="recipe-title">${escapeHTML(this._attrs.recipe_title)}</p><p class="muted">${escapeHTML(this._attrs.recipe_description)}</p>
      <div class="actions">${this._button("feed", "feed", true)}${this._button("prepared", "prepared")}</div>
      <p class="footnote">${copy(this._ui.intro)}</p></ha-card>`;
  }

  _stats() {
    const done = this._timeline.filter(finished).length;
    const next = this._state("next_step")?.state;
    const nextTitle = next && !["unknown", "unavailable"].includes(next) ? next : this._text("no_next");
    return `<div class="stats">
      <div class="card stat">${icon("check-circle-outline")}<p class="stat-label">${escapeHTML(this._text("steps"))}</p><p class="stat-value">${done} / ${this._timeline.length}</p></div>
      <div class="card stat">${icon("arrow-right-circle-outline")}<p class="stat-label">${escapeHTML(this._text("next"))}</p><p class="stat-value">${escapeHTML(nextTitle)}</p></div>
      <div class="card stat">${icon("clock-alert-outline")}<p class="stat-label">${escapeHTML(this._text("overdue"))}</p><p class="stat-value" data-overdue-count>0</p></div>
      <div class="card stat">${icon("calendar-clock")}<p class="stat-label">${escapeHTML(this._text("due"))}</p><p class="stat-value">${escapeHTML(this._date(this._step.due_at))}</p></div>
    </div>`;
  }

  _timelineCard() {
    const currentIndex = this._timeline.findIndex((step) => step.id === this._step.step_id);
    const start = Math.max(0, currentIndex < 0 ? this._timeline.length - 5 : currentIndex - 1);
    const visibleStart = Math.min(start, Math.max(0, this._timeline.length - 5));
    return `<ha-card class="timeline"><div class="section-head"><h2>${escapeHTML(this._text("timeline"))}</h2><span class="section-icon">${icon("format-list-checks")}</span></div>
      <p class="muted timeline-intro">${copy(this._ui.estimates || this._text("check"))}</p>
      ${!this._timeline.length ? `<p class="muted">${escapeHTML(this._text("timeline_empty"))}</p>` : `<ol>${this._timeline.map((step, index) => {
        const isCurrent = this._running && step.id === this._step.step_id;
        const stepState = finished(step) ? (step.state === "done" ? "done_state" : "skipped") : isCurrent ? "active_step" : "upcoming";
        return `<li class="step ${finished(step) ? step.state : "upcoming"} ${isCurrent ? "current" : ""} ${step.reference ? "reference" : ""}" data-step="${index}" ${isCurrent ? 'aria-current="step"' : ""}
          ${!this._expandedTimeline && (index < visibleStart || index >= visibleStart + 5) ? "hidden" : ""}>
          <span class="step-dot" aria-hidden="true">${finished(step) ? (step.state === "done" ? "✓" : "−") : isCurrent ? "●" : ""}</span>
          <p class="step-title">${escapeHTML(step.title)}</p><span class="step-state" data-step-state>${escapeHTML(this._text(stepState))}</span>
          <time datetime="${escapeHTML(step.completed_at || step.due_at)}">${escapeHTML(this._text(step.completed_at ? "actual" : "due"))} · ${escapeHTML(this._date(step.completed_at || step.due_at))}</time>
          <details data-detail="step-${index}"><summary>${escapeHTML(this._text("details"))}</summary>
            <p class="due-time">${escapeHTML(this._text("plan"))} · ${escapeHTML(this._date(step.planned_at))}<br>
              ${escapeHTML(this._text("due"))} · ${escapeHTML(this._date(step.due_at))}<br>
              ${escapeHTML(step.state_label)}${step.reference ? ` · ${escapeHTML(this._text("reference"))}` : ""}</p>
          </details></li>`;
      }).join("")}</ol>`}
      ${this._timeline.length > 5 ? `<button type="button" class="secondary timeline-toggle" data-action="timeline" aria-expanded="${!!this._expandedTimeline}">
        ${escapeHTML(this._text(this._expandedTimeline ? "collapse_timeline" : "show_timeline"))}${!this._expandedTimeline ? ` · ${this._timeline.length}` : ""}</button>` : ""}</ha-card>`;
  }

  _recipe() {
    const ingredients = Array.isArray(this._attrs.ingredients) ? this._attrs.ingredients : [];
    let url;
    try { url = new URL(this._attrs.recipe_url); } catch { /* Missing source URL. */ }
    const link = url && ["https:", "http:"].includes(url.protocol) ? `<p><a href="${escapeHTML(url.href)}" target="_blank" rel="noopener noreferrer">${escapeHTML(this._text("source"))} ↗</a></p>` : "";
    return this._disclosure("ingredients", "ingredients", "bowl-mix-outline", `<ul>${ingredients.map((item) => `<li>${copy(item)}</li>`).join("")}</ul>`) +
      this._disclosure("instructions", "instructions", "book-open-page-variant-outline", `
        ${this._step.instructions ? `<p>${copy(this._step.instructions)}</p>` : ""}
        <p>${copy(this._ui.attribution)} ${copy(this._ui.source)}</p>${link}<p>${copy(this._ui.method)}</p>
        <p>${copy(this._ui.baking)}</p><div class="safety">${icon("heat-wave")}<p>${copy(this._ui.safety)}</p></div>`);
  }

  _diagnostics() {
    return this._disclosure("diagnostics", "diagnostics", "information-outline", `<dl>${[
      ["bake", this._attrs.bake_id], ["starter", this._attrs.starter_id],
      ["workflow", this._attrs.workflow_label], ["last_sync", this._date(this._attrs.last_sync)],
    ].map(([label, value]) => `<dt>${escapeHTML(this._text(label))}</dt><dd>${escapeHTML(value || this._text("none"))}</dd>`).join("")}</dl>`);
  }

  _tick() {
    if (!this.isConnected || !this._hass || !this._available) return;
    const connected = this._isConnected();
    if (connected !== this._connected) { this._render(); return; }
    const now = Date.now();
    const due = timestamp(this._step.due_at);
    const delta = due - now;
    const timer = this.shadowRoot.querySelector("[data-countdown]");
    if (timer) {
      const paused = this._status === "paused";
      const valid = Number.isFinite(due);
      const seconds = Math.floor(Math.abs(delta) / 1000);
      const pad = (n) => String(n).padStart(2, "0");
      timer.textContent = paused ? this._text("paused_timer") : !valid ? "—" :
        `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor(seconds / 60) % 60)}:${pad(seconds % 60)}`;
      timer.classList.toggle("paused", paused);
      const label = this.shadowRoot.querySelector("[data-countdown-label]");
      label.textContent = this._text(paused ? "paused" : delta < -1000 ? "late" : delta <= 0 ? "due_now" : "next_action");
      const actionable = this._status === "active" && !!this._view.bake_id && !!this._view.step_id && valid && delta <= 0;
      for (const action of ["complete", "snooze"]) {
        const button = this.shadowRoot.querySelector(`[data-action="${action}"]`);
        if (button) button.disabled = !actionable || this._busy || !connected;
      }
      const waiting = this.shadowRoot.querySelector("[data-waiting]");
      waiting.textContent = this._status === "active" && !actionable ? this._text("waiting") : "";
      waiting.hidden = !waiting.textContent;
    }
    this.shadowRoot.querySelectorAll("[data-step]").forEach((item) => {
      const step = this._timeline[Number(item.dataset.step)];
      const overdue = this._running && !finished(step) && timestamp(step.due_at) < now;
      item.classList.toggle("overdue", overdue);
      const stepState = finished(step) ? (step.state === "done" ? "done_state" : "skipped") :
        step.id === this._step.step_id && this._running ? "active_step" : "upcoming";
      item.querySelector("[data-step-state]").textContent = `${this._text(stepState)}${overdue ? ` · ${this._text("overdue")}` : ""}`;
    });
    const count = this.shadowRoot.querySelector("[data-overdue-count]");
    if (count) count.textContent = String(this._state("overdue_count")?.state?.match(/^\d+$/)?.[0] ?? 0);
  }

  async _act(action) {
    if (action === "timeline") {
      this._expandedTimeline = !this._expandedTimeline;
      this._render();
      return;
    }
    if (this._busy || !this._connected || !this._available) return;
    if (action === "cancel" && !window.confirm(this._text("cancel_confirm"))) return;
    let service, data;
    if (action === "retry") {
      if (!this._retry) return;
      ({ service, data } = this._retry);
    } else if (["feed", "prepared"].includes(action)) {
      service = "start_bake";
      data = { starter_workflow: action === "prepared" ? "prepared" : "feed" };
    } else {
      data = { bake_id: this._view.bake_id };
      if (["complete", "snooze"].includes(action)) {
        service = action === "complete" ? "complete_step" : "snooze_step";
        data.step_id = this._view.step_id;
        if (action === "snooze") data.minutes = 10;
      } else if (["pause", "resume", "cancel"].includes(action)) service = `${action}_bake`;
      else return;
    }
    this._busy = true;
    this._focusAction = action;
    this._error = "";
    this._render();
    try {
      await this._hass.callService("bread_assistant", service, data);
      this._retry = undefined;
    } catch (error) {
      this._error = error?.message || this._text("action_error");
      this._retry = { service, data }; // Retain captured IDs: a retry cannot complete a different step.
    } finally {
      this._busy = false;
      this._render();
      this._focusAction = undefined;
    }
  }
}

if (!customElements.get("bread-assistant-card")) customElements.define("bread-assistant-card", BreadAssistantCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "bread-assistant-card")) {
  window.customCards.push({ type: "bread-assistant-card", name: "Bread Assistant", description: "Bake progress, countdown, actions and recipe timeline.", preview: false });
}
