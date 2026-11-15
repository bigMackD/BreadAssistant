// All selectors live inside the card's shadow root. Public overrides are optional.
export const styles = `
  :host {
    --ba-accent: var(--bread-assistant-accent-color, var(--warning-color, #d48216));
    --ba-ink: color-mix(in srgb, var(--ba-accent) 52%, var(--primary-text-color, #24211d));
    --ba-soft: color-mix(in srgb, var(--ba-accent) 10%, transparent);
    --ba-text: var(--primary-text-color, #24211d);
    --ba-muted: var(--secondary-text-color, #66615a);
    --ba-line: var(--divider-color, rgba(127,127,127,.18));
    --ba-radius: var(--ha-card-border-radius, 22px);
    display: block; color: var(--ba-text); container-type: inline-size;
    font-family: var(--primary-font-family, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
    -webkit-tap-highlight-color: transparent;
  }
  * { box-sizing: border-box; }
  [hidden] { display: none !important; }
  .shell { max-width: 1160px; margin: 0 auto; padding: 24px 20px 32px; }
  header { display: flex; align-items: center; gap: 14px; margin-bottom: 28px; }
  .brand-icon { display: grid; place-items: center; width: 46px; height: 46px; border-radius: 15px; background: var(--ba-soft); color: var(--ba-ink); flex-shrink: 0; }
  ha-icon { --mdc-icon-size: 24px; }
  .eyebrow { color: var(--ba-muted); font-size: 11px; font-weight: 650; letter-spacing: .13em; text-transform: uppercase; margin: 0 0 5px; }
  h1, h2, h3, p { margin: 0; }
  h1, h2, h3, p, li { overflow-wrap: anywhere; }
  h1 { font-size: 27px; font-weight: 720; letter-spacing: -.045em; line-height: 1.15; }
  h2 { font-size: 22px; font-weight: 680; letter-spacing: -.03em; line-height: 1.25; text-wrap: balance; }
  h3 { font-size: 15px; font-weight: 650; line-height: 1.4; }
  p, li { font-size: 14px; line-height: 1.65; }
  .muted { color: var(--ba-muted); }
  .badge { display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 7px 11px; background: var(--ba-soft); color: var(--ba-ink); font-size: 12px; font-weight: 600; line-height: 1.4; }
  .status { margin-left: auto; max-width: 42%; }
  .badge::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
  .layout { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 22px; align-items: start; }
  .column { display: grid; gap: 18px; min-width: 0; }
  ha-card, .card {
    display: block; background: var(--ha-card-background, var(--card-background-color, #fff));
    border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--ba-line));
    border-radius: var(--ba-radius); box-shadow: var(--ha-card-box-shadow, 0 4px 24px rgba(0,0,0,.035));
    overflow: hidden; color: inherit;
  }
  .hero { padding: 28px; position: relative; animation: ba-enter .2s ease-out; }
  @keyframes ba-enter { from { opacity: .65; } to { opacity: 1; } }
  .hero-top { display: flex; align-items: center; gap: 24px; margin-bottom: 26px; }
  .ring { width: 132px; height: 132px; position: relative; flex-shrink: 0; }
  .ring svg { width: 100%; height: 100%; transform: rotate(-90deg); overflow: visible; }
  .ring circle { fill: none; stroke-width: 7; }
  .ring-track { stroke: var(--ba-line); }
  .ring-progress { stroke: var(--ba-accent); stroke-linecap: round; transition: stroke-dasharray .6s ease; }
  .ring-value { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; flex-direction: column; }
  .percent { font-size: 31px; font-weight: 700; letter-spacing: -.05em; font-variant-numeric: tabular-nums; }
  .ring-label { font-size: 11px; color: var(--ba-muted); margin-top: 3px; max-width: 90px; text-align: center; }
  .recipe-title { font-size: 17px; line-height: 1.45; letter-spacing: -.02em; font-weight: 620; margin-top: 10px; }
  .hero-title { min-width: 0; }
  .timer-block { border-top: 1px solid var(--ba-line); border-bottom: 1px solid var(--ba-line); padding: 22px 0; margin-bottom: 24px; }
  .countdown { font-size: clamp(38px, 9cqi, 55px); font-weight: 650; letter-spacing: -.05em; font-variant-numeric: tabular-nums; line-height: 1.2; margin: 5px 0 8px; }
  .countdown.paused { font-size: 27px; line-height: 1.35; }
  .due-time { font-size: 12px; color: var(--ba-muted); }
  .stage { margin: 10px 0 12px; }
  .stage-copy { color: var(--ba-muted); margin-bottom: 20px; }
  .actions { display: grid; gap: 10px; }
  button {
    font: inherit; font-size: 14px; font-weight: 620; border: 1px solid transparent; border-radius: 14px;
    min-height: 48px; padding: 12px 17px; cursor: pointer; touch-action: manipulation;
    color: var(--ba-text); background: var(--secondary-background-color, rgba(127,127,127,.09));
    transition: filter .15s ease, transform .15s ease; line-height: 1.4;
  }
  button:hover:not(:disabled) { filter: brightness(.94); }
  button:active:not(:disabled) { transform: scale(.985); }
  button:focus-visible, summary:focus-visible, a:focus-visible { outline: 3px solid var(--primary-color, #0a84ff); outline-offset: 4px; }
  button.primary { background: var(--ba-accent); color: #241700; }
  button.secondary { background: var(--ba-soft); color: var(--ba-ink); }
  button:disabled { opacity: .45; cursor: default; }
  .footnote { font-size: 12px; color: var(--ba-muted); margin-top: 14px; line-height: 1.6; }
  .stats { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
  .stat { padding: 18px; min-width: 0; }
  .stat ha-icon { color: var(--ba-ink); --mdc-icon-size: 20px; margin-bottom: 10px; }
  .stat-label { color: var(--ba-muted); font-size: 12px; margin-bottom: 7px; }
  .stat-value { font-size: 15px; font-weight: 650; line-height: 1.45; overflow-wrap: anywhere; }
  .controls { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
  .controls button { background: transparent; color: var(--ba-muted); padding-inline: 12px; font-size: 12px; }
  .controls .danger { color: var(--error-color, #c43830); }
  .notice { padding: 18px 20px; border-left: 3px solid var(--ba-accent); }
  .shell > [data-connection] > .notice, .shell > [data-action-error] > .notice { margin-bottom: 18px; }
  .notice p { margin-top: 6px; }
  .error { border-left-color: var(--error-color, #c43830); }
  .error h3 { color: var(--error-color, #c43830); }
  .error button { margin-top: 12px; }
  .timeline { padding: 24px; }
  .section-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 10px; }
  .section-head h2 { font-size: 18px; }
  .section-icon { color: var(--ba-ink); }
  .timeline-intro { font-size: 12px; margin-bottom: 24px; }
  .timeline-toggle { width: 100%; margin-top: 20px; }
  ol { list-style: none; padding: 0; margin: 0; }
  .step { position: relative; padding: 0 0 24px 32px; min-width: 0; }
  .step:not(:last-child)::before { content: ''; position: absolute; left: 8px; top: 21px; bottom: 2px; width: 1px; background: var(--ba-line); }
  .step:last-child { padding-bottom: 0; }
  .step-dot { position: absolute; left: 0; top: 2px; width: 18px; height: 18px; border-radius: 50%; border: 1.5px solid var(--ba-line); color: var(--ba-muted); font-size: 11px; line-height: 15px; text-align: center; background: var(--ha-card-background, var(--card-background-color, #fff)); }
  .step.done .step-dot, .step.skipped .step-dot { color: var(--success-color, #268647); border-color: currentColor; }
  .step.current .step-dot { background: var(--ba-accent); border-color: var(--ba-accent); color: #241700; box-shadow: 0 0 0 4px var(--ba-soft); }
  .step.overdue .step-dot { color: var(--error-color, #c43830); border-color: currentColor; }
  .step.current.overdue .step-dot { background: var(--error-color, #c43830); color: var(--card-background-color, #fff); border-color: var(--error-color, #c43830); }
  .step-title { font-size: 14px; font-weight: 500; line-height: 1.5; }
  .step.reference .step-title, .step.current .step-title { font-weight: 680; }
  .step.done .step-title, .step.skipped .step-title { color: var(--ba-muted); }
  .step-state { display: inline-block; color: var(--ba-muted); font-size: 11px; margin-top: 4px; }
  .step.current .step-state { color: var(--ba-ink); font-weight: 650; }
  .step.overdue .step-state { color: var(--error-color, #c43830); }
  .step time { display: block; font-size: 12px; color: var(--ba-muted); line-height: 1.6; margin-top: 4px; }
  .step details { margin-top: 6px; }
  .step summary { font-size: 12px; color: var(--ba-muted); min-height: 44px; padding: 12px 0; }
  details.group > summary { display: flex; align-items: center; gap: 12px; padding: 20px; list-style: none; min-height: 62px; font-size: 14px; font-weight: 650; }
  details.group > summary::-webkit-details-marker { display: none; }
  details.group > summary::after { content: '+'; font-size: 20px; font-weight: 400; color: var(--ba-muted); margin-left: auto; }
  details.group[open] > summary::after { content: '−'; }
  summary { cursor: pointer; touch-action: manipulation; }
  .detail-body { padding: 0 22px 22px; }
  .detail-body p + p { margin-top: 12px; }
  .detail-body ul { margin: 0; padding-left: 20px; }
  .detail-body li + li { margin-top: 12px; }
  a { color: var(--primary-color, #0a84ff); text-underline-offset: 3px; overflow-wrap: anywhere; }
  .safety { background: var(--ba-soft); border-radius: 12px; padding: 14px; margin-top: 16px; }
  .safety ha-icon { --mdc-icon-size: 18px; color: var(--ba-ink); margin-right: 5px; }
  .empty { text-align: center; padding: 32px 26px; }
  .empty .brand-icon { margin: 0 auto 24px; width: 68px; height: 68px; border-radius: 22px; }
  .empty h2 { font-size: 28px; margin-bottom: 14px; }
  .empty .recipe-title { margin: 22px 0 8px; }
  .empty .actions { margin-top: 24px; }
  dl { margin: 0; font-size: 12px; }
  dt { color: var(--ba-muted); margin-top: 12px; }
  dd { margin: 4px 0 0; overflow-wrap: anywhere; line-height: 1.6; }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; border: 0; }
  @container (max-width: 760px) {
    .layout { grid-template-columns: minmax(0, 1fr); gap: 18px; }
    .shell { max-width: 600px; padding: 20px 12px 28px; }
    header { margin-bottom: 22px; }
    h1 { font-size: 24px; }
    .status { font-size: 11px; padding: 6px 9px; }
  }
  @container (max-width: 400px) {
    .shell { padding: 16px 4px 24px; }
    header { gap: 10px; flex-wrap: wrap; }
    .brand-icon { width: 40px; height: 40px; }
    h1 { font-size: 23px; }
    .eyebrow { font-size: 10px; }
    header .status { max-width: 100%; margin: 0 0 0 50px; }
    .hero { padding: 22px; }
    .hero-top { gap: 18px; }
    .ring { width: 112px; height: 112px; }
    .percent { font-size: 27px; }
    .recipe-title { font-size: 15px; }
    .timeline { padding: 22px; }
  }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { transition: none !important; animation: none !important; }
  }
  @media (forced-colors: active) {
    .ring-progress { stroke: Highlight; }
    button, .step-dot { border: 1px solid ButtonText; }
  }
`;
