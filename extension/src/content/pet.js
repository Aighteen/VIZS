// Classic script injected only when the user clicks the VIZS toolbar button (activeTab).
// Runs in the extension's isolated world. It never reads storage or the pairing token, and it
// never sends the page URL: the service worker reads it from sender.tab.url.
(function () {
  "use strict";
  if (globalThis.__vizsPet) {
    globalThis.__vizsPet.show();
    return;
  }
  const R = globalThis.VIZS_RENDER;
  const CSS = globalThis.VIZS_STYLES;
  if (!R || typeof CSS !== "string") return;

  const doc = document;
  const MARGIN = 8;
  const STEP = 12;
  const BIG_STEP = 60;

  let state = { name: "idle", token: null, viewModel: null, error: null };
  let requestHref = null;
  let watchedHref = location.href;
  let sending = false;
  let panelEl = null;
  let pos = null;
  let saveTimer = null;
  const terminalTokens = new Set();

  // ---- Host + closed shadow root ----
  const host = doc.createElement("vizs-pet-root");
  const hostStyle = {
    all: "initial", position: "fixed", "z-index": "2147483647", left: "0px", bottom: "0px", top: "auto", right: "auto",
    display: "block", margin: "0", padding: "0", border: "0", width: "auto", height: "auto",
    transform: "none", opacity: "1", visibility: "visible", "pointer-events": "auto",
  };
  for (const k of Object.keys(hostStyle)) host.style.setProperty(k, hostStyle[k], "important");
  const shadow = host.attachShadow({ mode: "closed" });
  // Constructable stylesheet: not subject to the page's inline-style CSP; <style> as fallback.
  try {
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(CSS);
    shadow.adoptedStyleSheets = [sheet];
  } catch (e) {
    const style = doc.createElement("style");
    style.textContent = CSS;
    shadow.appendChild(style);
  }

  const wrap = R.el(doc, "div", { className: "vizs", attrs: { "data-state": "idle" } });
  const card = R.el(doc, "div", { className: "card" });
  const statusText = R.el(doc, "p", { className: "status", attrs: { role: "status", "aria-live": "polite" } });

  // Idle controls
  const idleBox = R.el(doc, "div");
  const priceLabel = R.el(doc, "label", { className: "price", text: "Price you see (optional, USD)", attrs: { for: "vizs-price" } });
  const priceInput = R.el(doc, "input", {
    className: "price",
    attrs: { id: "vizs-price", type: "text", inputmode: "decimal", autocomplete: "off", maxlength: "20", placeholder: "e.g. 89.99" },
  });
  const checkBtn = R.el(doc, "button", { className: "btn primary", text: "Check seller", attrs: { type: "button" } });
  const hint = R.el(doc, "p", { className: "hint", attrs: { "aria-live": "polite" } });
  idleBox.append(priceLabel, priceInput, checkBtn, hint);

  // Finished bubble
  const bubble = R.el(doc, "button", { className: "bubble", text: "Check complete. View result", attrs: { type: "button" } });

  // Error controls
  const errorBox = R.el(doc, "div");
  const errorMsg = R.el(doc, "p", { className: "error-msg" });
  const retryBtn = R.el(doc, "button", { className: "btn primary", text: "Retry", attrs: { type: "button" } });
  const settingsBtn = R.el(doc, "button", { className: "btn", text: "Open settings", attrs: { type: "button" } });
  errorBox.append(errorMsg, R.el(doc, "div", { className: "row" }, [retryBtn, settingsBtn]));

  const note = R.el(doc, "p", { className: "note" });
  card.append(statusText, idleBox, bubble, errorBox, note);

  const petBtn = R.el(doc, "button", {
    className: "pet",
    attrs: { type: "button", "aria-label": "VIZS pet. Drag or use arrow keys to move." },
  });
  petBtn.appendChild(R.renderMascot(doc));
  const dismissBtn = R.el(doc, "button", { className: "dismiss", text: "×", attrs: { type: "button", "aria-label": "Dismiss VIZS pet" } });
  const petRow = R.el(doc, "div", { className: "petrow" }, [petBtn, dismissBtn]);
  wrap.append(card, petRow);
  shadow.appendChild(wrap);
  (doc.body || doc.documentElement).appendChild(host);

  // ---- Reduced motion ----
  function applyMotion() {
    wrap.setAttribute("data-motion", R.prefersReducedMotion(window) ? "reduced" : "full");
  }
  applyMotion();
  let motionQuery = null;
  try {
    motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    motionQuery.addEventListener("change", applyMotion);
  } catch (e) {
    motionQuery = null;
  }

  // ---- Messaging ----
  async function send(message) {
    try {
      return await chrome.runtime.sendMessage(message);
    } catch (e) {
      return { ok: false, error: "extension_unavailable" };
    }
  }

  function onWorkerMessage(message, sender) {
    if (!R.isTrustedWorkerSender(sender, chrome.runtime.id)) return;
    if (!R.isValidStateMessage(message)) return;
    applyState(message.state, true);
  }
  chrome.runtime.onMessage.addListener(onWorkerMessage);

  function applyState(next, pushed) {
    if (next.name === "finished" || next.name === "error") {
      if (next.token !== null && pushed && next.token !== state.token && !sending) return; // stale push
      if (requestHref !== null && location.href !== requestHref) {
        // Page changed since this check started: never show the old result here.
        resetToIdle(true);
        return;
      }
      if (next.token) terminalTokens.add(next.token);
    }
    if (next.name === "searching" && terminalTokens.has(next.token)) return; // already settled
    if (next.name === "idle" && pushed && state.name !== "searching") return;
    state = next;
    render();
  }

  // ---- Rendering ----
  function show(elm, visible) {
    elm.classList.toggle("hidden", !visible);
  }

  function render() {
    wrap.setAttribute("data-state", state.name);
    show(idleBox, state.name === "idle");
    show(bubble, state.name === "finished");
    show(errorBox, state.name === "error");
    checkBtn.disabled = state.name === "searching" || sending;
    priceInput.disabled = state.name === "searching";
    if (state.name !== "finished") closePanel(false);
    switch (state.name) {
      case "idle":
        statusText.textContent = "Want me to check this seller?";
        petBtn.setAttribute("aria-label", "VIZS pet, ready. Drag or use arrow keys to move.");
        break;
      case "searching":
        statusText.textContent = "Checking seller…";
        petBtn.setAttribute("aria-label", "VIZS pet, checking seller. Drag or use arrow keys to move.");
        break;
      case "finished":
        statusText.textContent = state.viewModel && state.viewModel.insufficient
          ? "Done: not enough evidence for a confident answer."
          : "Done: seller check finished.";
        petBtn.setAttribute("aria-label", "VIZS pet, result ready. Press Enter to open it. Arrow keys move the pet.");
        break;
      case "error":
        statusText.textContent = "Hmm, the check did not finish.";
        errorMsg.textContent = state.error.message;
        show(retryBtn, state.error.retryable !== false);
        show(settingsBtn, Boolean(state.error.showSettings));
        petBtn.setAttribute("aria-label", "VIZS pet, check failed. Drag or use arrow keys to move.");
        break;
    }
    requestAnimationFrame(clampIntoView);
  }

  function openPanel() {
    if (state.name !== "finished" || !state.viewModel) return;
    closePanel(false);
    panelEl = R.renderPanel(doc, state.viewModel);
    const close = R.el(doc, "button", { className: "dismiss", text: "×", attrs: { type: "button", "aria-label": "Close result" } });
    close.addEventListener("click", () => closePanel(true));
    panelEl.firstChild.appendChild(close);
    shadow.appendChild(panelEl);
    placePanel();
    close.focus();
  }

  // Put the panel beside the pet when there is room; narrow viewports use the CSS bottom sheet.
  function placePanel() {
    if (!panelEl || window.innerWidth <= 480) return;
    const wr = wrap.getBoundingClientRect();
    const pr = panelEl.getBoundingClientRect();
    const gap = 12;
    let left;
    if (wr.left - pr.width - gap >= MARGIN) left = wr.left - pr.width - gap;
    else if (wr.right + gap + pr.width <= window.innerWidth - MARGIN) left = wr.right + gap;
    else left = R.clamp(wr.left, MARGIN, window.innerWidth - pr.width - MARGIN);
    const top = R.clamp(wr.bottom - pr.height, MARGIN, window.innerHeight - pr.height - MARGIN);
    panelEl.style.setProperty("left", left + "px");
    panelEl.style.setProperty("top", top + "px");
    panelEl.style.setProperty("right", "auto");
    panelEl.style.setProperty("bottom", "auto");
  }

  function closePanel(returnFocus) {
    if (!panelEl) return;
    panelEl.remove();
    panelEl = null;
    if (returnFocus) (state.name === "finished" ? bubble : petBtn).focus();
  }

  // ---- Actions ----
  async function startCheck() {
    if (state.name === "searching" || sending) return; // one request per tab; SW also enforces
    hint.textContent = "";
    note.textContent = "";
    sending = true;
    requestHref = location.href;
    checkBtn.disabled = true;
    const price = priceInput.value.trim();
    const response = await send(price ? { type: "check", price } : { type: "check" });
    sending = false;
    if (!response || !response.ok || !response.state) {
      state = { name: "error", token: null, viewModel: null, error: { message: "VIZS could not start the check. Reload the page and try again.", retryable: true } };
      render();
      return;
    }
    applyState(response.state, false);
  }

  function resetToIdle(notifyWorker) {
    const wasSearching = state.name === "searching";
    state = { name: "idle", token: null, viewModel: null, error: null };
    requestHref = null;
    closePanel(false);
    render();
    if (notifyWorker) send({ type: "navigated" });
    if (wasSearching) note.textContent = "The page changed, so the earlier check was discarded.";
  }

  function dismiss() {
    send({ type: "dismiss" });
    clearInterval(hrefTimer);
    clearTimeout(saveTimer);
    chrome.runtime.onMessage.removeListener(onWorkerMessage);
    if (motionQuery) motionQuery.removeEventListener("change", applyMotion);
    window.removeEventListener("resize", clampIntoView);
    host.remove();
    delete globalThis.__vizsPet;
  }

  checkBtn.addEventListener("click", startCheck);
  retryBtn.addEventListener("click", startCheck); // explicit retry only; never automatic
  priceInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") startCheck();
  });
  settingsBtn.addEventListener("click", () => send({ type: "openOptions" }));
  bubble.addEventListener("click", openPanel);
  dismissBtn.addEventListener("click", dismiss);
  shadow.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && panelEl) {
      e.stopPropagation();
      closePanel(true);
    }
  });

  // SPA navigation (URL change without reload) also discards pending/finished results.
  const hrefTimer = setInterval(() => {
    if (location.href === watchedHref) return;
    watchedHref = location.href;
    if (state.name !== "idle") resetToIdle(true);
  }, 1000);

  // ---- Position: drag + keyboard ----
  // pos.x = distance from the left edge, pos.y = distance from the bottom edge, so the pet stays
  // put while the speech card above it grows or shrinks between states.
  function setPos(x, y, persist) {
    const rect = wrap.getBoundingClientRect();
    const w = rect.width || 260;
    const h = rect.height || 160;
    pos = {
      x: R.clamp(x, MARGIN, window.innerWidth - w - MARGIN),
      y: R.clamp(y, MARGIN, window.innerHeight - h - MARGIN),
    };
    host.style.setProperty("left", pos.x + "px", "important");
    host.style.setProperty("bottom", pos.y + "px", "important");
    if (persist) {
      clearTimeout(saveTimer);
      saveTimer = setTimeout(() => send({ type: "savePosition", x: pos.x, y: pos.y }), 300);
    }
  }
  function clampIntoView() {
    if (pos) setPos(pos.x, pos.y, false);
    placePanel();
  }
  window.addEventListener("resize", clampIntoView);

  let drag = null;
  let suppressClick = false;
  petBtn.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    drag = { startX: e.clientX, startY: e.clientY, originX: pos.x, originY: pos.y, moved: false };
    petBtn.setPointerCapture(e.pointerId);
  });
  petBtn.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.startX;
    const dy = e.clientY - drag.startY;
    if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 5) return;
    drag.moved = true;
    setPos(drag.originX + dx, drag.originY - dy, false);
  });
  function endDrag(e) {
    if (!drag) return;
    if (drag.moved) {
      suppressClick = true;
      setPos(pos.x, pos.y, true);
    }
    drag = null;
    try {
      petBtn.releasePointerCapture(e.pointerId);
    } catch (err) {
      /* already released */
    }
  }
  petBtn.addEventListener("pointerup", endDrag);
  petBtn.addEventListener("pointercancel", endDrag);
  petBtn.addEventListener("click", () => {
    if (suppressClick) {
      suppressClick = false;
      return;
    }
    if (state.name === "finished") openPanel();
    else if (state.name === "idle") priceInput.focus();
    else if (state.name === "error") retryBtn.focus();
  });
  petBtn.addEventListener("keydown", (e) => {
    const step = e.shiftKey ? BIG_STEP : STEP;
    const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] };
    const m = moves[e.key];
    if (!m) return;
    e.preventDefault();
    setPos(pos.x + m[0], pos.y + m[1], true);
  });

  // Initial position: stored preference (via the service worker) or bottom-right corner.
  setPos(window.innerWidth - 300, 24, false);
  send({ type: "getPosition" }).then((res) => {
    if (res && res.ok && res.position) setPos(res.position.x, res.position.y, false);
  });

  render();
  globalThis.__vizsPet = {
    show() {
      host.style.setProperty("display", "block", "important");
      petBtn.focus();
    },
  };
  petBtn.focus();
})();
