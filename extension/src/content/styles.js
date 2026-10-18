// Classic script (injected on toolbar click). Defines the pet's stylesheet inside the extension's
// isolated world; it is applied only inside the closed shadow root, so page CSS cannot restyle it.
(function (root) {
  "use strict";
  root.VIZS_STYLES = `
:host { all: initial; }
* { box-sizing: border-box; }
/* Tokens live on both roots: the panel is a sibling of .vizs, and the page cannot reach either. */
.vizs, .panel {
  --ink: #1f1a2e; --muted: #574f6b; --paper: #ffffff; --soft: #f4effc; --line: #d6cbea;
  --brand: #5b3f96; --brand-ink: #ffffff; --warn: #8a4b00; --warn-bg: #fff4e0;
  --bad: #9c1c1c; --bad-bg: #fdeaea; --good: #1d6b3a; --good-bg: #e6f5ea; --focus: #1a5fd6;
}
.vizs {
  font: 14px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  color: var(--ink);
  display: flex; flex-direction: column; align-items: flex-end; gap: 6px;
  width: 260px; pointer-events: auto;
}
button, input { font: inherit; color: inherit; }
button { cursor: pointer; }
:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }
.card {
  width: 100%; background: var(--paper); border: 1px solid var(--line); border-radius: 12px;
  padding: 10px 12px; box-shadow: 0 6px 20px rgba(31, 26, 46, 0.18);
}
.status { margin: 0 0 6px; font-weight: 600; }
.row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
label.price { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
input.price {
  width: 100%; padding: 6px 8px; border: 1px solid var(--line); border-radius: 8px; background: #fff; margin-bottom: 8px;
}
.btn {
  border: 1px solid var(--brand); border-radius: 8px; padding: 6px 12px; background: var(--paper); color: var(--brand);
}
.btn.primary { background: var(--brand); color: var(--brand-ink); }
.btn[disabled] { opacity: 0.6; cursor: default; }
.hint { margin: 6px 0 0; font-size: 12px; color: var(--bad); }
.hint:empty { display: none; }
.note { margin: 6px 0 0; font-size: 12px; color: var(--muted); }
.bubble {
  width: 100%; text-align: left; border: 2px solid var(--brand); background: var(--soft); border-radius: 12px; padding: 8px 10px;
}
.error-msg { margin: 0 0 8px; }
.petrow { display: flex; align-items: flex-start; gap: 4px; }
.pet {
  width: 72px; height: 72px; padding: 0; border: none; background: transparent; border-radius: 50%;
  cursor: grab; touch-action: none; user-select: none;
}
.pet:active { cursor: grabbing; }
.pet svg { width: 72px; height: 72px; display: block; overflow: visible; }
.dismiss {
  width: 28px; height: 28px; border-radius: 50%; border: 1px solid var(--line); background: var(--paper); line-height: 1; padding: 0;
}
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.hidden { display: none !important; }

/* Mascot states */
.mascot .glass, .mascot .qmark, .mascot .alert, .mascot .mouth-puzzled { display: none; }
.vizs[data-state="searching"] .mascot .glass { display: inline; }
.vizs[data-state="error"] .mascot .qmark, .vizs[data-state="error"] .mascot .mouth-puzzled { display: inline; }
.vizs[data-state="error"] .mascot .mouth-smile { display: none; }
.vizs[data-state="finished"] .mascot .alert { display: inline; }
.vizs[data-state="error"] .mascot .body-group { transform: rotate(-8deg); transform-origin: 32px 40px; }
.vizs[data-state="searching"] .mascot .body-group { animation: vizs-bob 0.9s ease-in-out infinite; }
.vizs[data-state="searching"] .mascot .glass { animation: vizs-sweep 1.6s ease-in-out infinite; transform-origin: 48px 46px; }
.vizs[data-state="finished"] .mascot .alert { animation: vizs-pop 1.2s ease-in-out infinite; transform-origin: 54px 10px; }
.vizs[data-state="idle"] .mascot .eyes { animation: vizs-blink 5s infinite; transform-origin: 32px 36px; }
@keyframes vizs-bob { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
@keyframes vizs-sweep { 0%, 100% { transform: rotate(-14deg); } 50% { transform: rotate(14deg); } }
@keyframes vizs-pop { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.15); } }
@keyframes vizs-blink { 0%, 94%, 100% { transform: scaleY(1); } 97% { transform: scaleY(0.1); } }

/* Static pet when the user prefers reduced motion (media query or detected flag). */
@media (prefers-reduced-motion: reduce) {
  .vizs *, .vizs *::before, .vizs *::after { animation: none !important; transition: none !important; }
}
.vizs[data-motion="reduced"] *, .vizs[data-motion="reduced"] *::before, .vizs[data-motion="reduced"] *::after {
  animation: none !important; transition: none !important;
}

/* Result panel */
.panel {
  position: fixed; right: 16px; bottom: 16px; text-align: left; width: min(400px, calc(100vw - 32px)); max-height: min(75vh, 640px);
  overflow: auto; background: var(--paper); color: var(--ink); border: 1px solid var(--line); border-radius: 14px;
  box-shadow: 0 12px 36px rgba(31, 26, 46, 0.28); padding: 14px 16px; z-index: 1;
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
.panel h2 { font-size: 16px; margin: 0; }
.panel h3 { font-size: 13px; margin: 14px 0 6px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
.panel h4 { font-size: 14px; margin: 0; }
.panel p { margin: 6px 0; }
.panel ul { margin: 4px 0; padding-left: 18px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.badge { display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 6px; border-radius: 6px; background: var(--soft); color: var(--brand); border: 1px solid var(--line); }
.badge.unverified { background: var(--warn-bg); color: var(--warn); border-color: #f0cf9a; }
.badge.sim { background: var(--bad-bg); color: var(--bad); border-color: #efb3b3; }
.banner { padding: 8px 10px; border-radius: 8px; font-weight: 600; }
.banner.sim { background: var(--bad-bg); color: var(--bad); }
.banner.info { background: var(--soft); color: var(--muted); font-weight: 400; }
.verdict { display: grid; grid-template-columns: auto 1fr; gap: 2px 10px; margin: 10px 0; }
.verdict dt { color: var(--muted); }
.verdict dd { margin: 0; font-weight: 600; }
.promise { border: 1px solid var(--line); border-radius: 10px; padding: 8px 10px; margin: 6px 0; }
.promise[data-status="conflicting"] { border-color: #e7a3a3; background: #fffafa; }
.promise-head { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.status-label { font-size: 12px; color: var(--muted); }
.promise[data-status="conflicting"] .status-label { color: var(--bad); font-weight: 600; }
blockquote { margin: 6px 0; padding: 4px 8px; border-left: 3px solid var(--line); background: var(--soft); white-space: pre-wrap; overflow-wrap: anywhere; }
.cite { font-size: 12px; color: var(--muted); display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.panel a { color: var(--focus); overflow-wrap: anywhere; }
.panel .disclaimer { font-size: 12px; color: var(--muted); border-top: 1px solid var(--line); padding-top: 8px; margin-top: 12px; }
.panel summary { cursor: pointer; font-size: 12px; color: var(--brand); }
@media (max-width: 480px) { .panel { right: 8px; left: 8px; bottom: 8px; width: auto; } }
`;
})(globalThis);
