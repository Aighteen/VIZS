// Per-tab request controller used by the service worker. All Chrome APIs are injected so the
// whole flow (duplicate clicks, stale results, error mapping) is testable in Node.
import { CLIENT_TIMEOUT_MS } from "./config.js";
import { isTrustedContentSender, parseCommand } from "./messages.js";
import { INITIAL_STATE, STATES, canStartRequest, reduce, snapshot } from "./pet-state.js";
import { buildEvaluateRequest, listingUrlFromSender, normalizePrice } from "./request.js";
import {
  ERROR_CODES, clientTimeoutError, errorForStatus, invalidResponseError, makeError, networkError, notPairedError,
  validateEvaluateResponse,
} from "./response.js";
import { buildPanelViewModel } from "./view-model.js";

const MAX_RESPONSE_BYTES = 512 * 1024;

export const DISMISS_NOTE =
  "Stopped waiting for this check. Work the backend already started may still finish, and any provider usage is not reversed.";

export class PetController {
  /**
   * @param {object} deps
   * @param {string} deps.runtimeId
   * @param {(url: string, init: object) => Promise<Response>} deps.fetchImpl
   * @param {() => Promise<{backendUrl: string|null, token: string|null}>} deps.loadSettings
   * @param {() => string} deps.newRequestId
   * @param {(tabId: number, message: object) => void|Promise<void>} deps.deliver
   * @param {(tabId: number) => Promise<string|undefined>} deps.getTabUrl
   */
  constructor(deps) {
    this.deps = {
      timeoutMs: CLIENT_TIMEOUT_MS,
      setTimer: (fn, ms) => setTimeout(fn, ms),
      clearTimer: (id) => clearTimeout(id),
      onActiveCountChange: () => {},
      savePosition: async () => {},
      getPosition: async () => null,
      openOptions: async () => {},
      ...deps,
    };
    this.tabs = new Map();
    this.active = 0;
  }

  stateFor(tabId) {
    return this.tabs.get(tabId)?.state ?? INITIAL_STATE;
  }

  /** Promise for the in-flight request of a tab (tests and diagnostics). */
  pending(tabId) {
    return this.tabs.get(tabId)?.pending ?? Promise.resolve();
  }

  async handle(rawMessage, sender) {
    if (!isTrustedContentSender(sender, this.deps.runtimeId)) return { ok: false, error: "untrusted_sender" };
    const cmd = parseCommand(rawMessage);
    if (!cmd) return { ok: false, error: "invalid_message" };
    const tabId = sender.tab.id;
    switch (cmd.type) {
      case "check":
        return this.#check(tabId, cmd, sender);
      case "dismiss":
      case "navigated": {
        const discarded = this.discard(tabId);
        return { ok: true, state: snapshot(INITIAL_STATE), discarded, note: discarded ? DISMISS_NOTE : null };
      }
      case "getState":
        return { ok: true, state: snapshot(this.stateFor(tabId)) };
      case "savePosition":
        await this.deps.savePosition({ x: cmd.x, y: cmd.y });
        return { ok: true };
      case "getPosition":
        return { ok: true, position: await this.deps.getPosition() };
      case "openOptions":
        await this.deps.openOptions();
        return { ok: true };
      default:
        return { ok: false, error: "invalid_message" };
    }
  }

  /** Forget a tab's request (dismissal, navigation, tab closed). Returns true if one was pending. */
  discard(tabId) {
    const entry = this.tabs.get(tabId);
    if (!entry) return false;
    const wasSearching = entry.state.name === STATES.SEARCHING;
    this.tabs.delete(tabId);
    if (entry.abort) entry.abort.abort();
    return wasSearching;
  }

  #setState(tabId, entry, event) {
    entry.state = reduce(entry.state, event);
    this.tabs.set(tabId, entry);
    return snapshot(entry.state);
  }

  #fail(tabId, entry, token, error) {
    return { ok: true, state: this.#setState(tabId, entry, { type: "FAIL", token, error }) };
  }

  async #check(tabId, cmd, sender) {
    const entry = this.tabs.get(tabId) ?? { state: INITIAL_STATE };
    if (!canStartRequest(entry.state)) {
      return { ok: true, ignored: true, state: snapshot(entry.state) }; // one in-flight request per tab
    }
    const price = normalizePrice(cmd.price);
    if (!price.ok) return this.#fail(tabId, entry, null, makeError(ERROR_CODES.INVALID_INPUT, price.error));
    const listing = listingUrlFromSender(sender);
    if (!listing.ok) return this.#fail(tabId, entry, null, makeError(ERROR_CODES.UNSUPPORTED_PAGE, listing.error));

    // Reserve the slot synchronously, before any await, so a racing second click is ignored.
    const token = this.deps.newRequestId();
    this.#setState(tabId, entry, { type: "CHECK", token });

    const settings = await this.deps.loadSettings();
    if (this.tabs.get(tabId) !== entry || entry.state.token !== token) {
      return { ok: true, state: snapshot(this.stateFor(tabId)) }; // dismissed meanwhile
    }
    if (!settings?.backendUrl || !settings?.token) return this.#fail(tabId, entry, token, notPairedError());

    const req = buildEvaluateRequest({
      backendUrl: settings.backendUrl, token: settings.token, listingUrl: listing.value, price: price.value, requestId: token,
    });
    if (!req.ok) return this.#fail(tabId, entry, token, makeError(ERROR_CODES.INVALID_INPUT, req.error));

    entry.abort = new AbortController();
    entry.pending = this.#run(tabId, entry, token, req, listing.value);
    return { ok: true, state: snapshot(entry.state) };
  }

  async #run(tabId, entry, token, req, listingUrl) {
    const abort = entry.abort;
    let timedOut = false;
    const timer = this.deps.setTimer(() => {
      timedOut = true;
      abort.abort();
    }, this.deps.timeoutMs);
    this.#activeDelta(1);
    let event;
    try {
      const res = await this.deps.fetchImpl(req.url, { ...req.init, signal: abort.signal });
      if (!res.ok) {
        event = { type: "FAIL", token, error: errorForStatus(res.status) };
      } else {
        event = await this.#parse(res, token);
      }
    } catch {
      event = { type: "FAIL", token, error: timedOut ? clientTimeoutError() : networkError() };
    } finally {
      this.deps.clearTimer(timer);
      this.#activeDelta(-1);
    }
    return this.#settle(tabId, entry, token, listingUrl, event);
  }

  async #parse(res, token) {
    let payload;
    try {
      const text = await res.text();
      if (text.length > MAX_RESPONSE_BYTES) return { type: "FAIL", token, error: invalidResponseError() };
      payload = JSON.parse(text);
    } catch {
      return { type: "FAIL", token, error: invalidResponseError() };
    }
    const result = validateEvaluateResponse(payload, token);
    if (!result.ok) return { type: "FAIL", token, error: invalidResponseError() };
    return { type: "RESULT", token, viewModel: buildPanelViewModel(result.assessment) };
  }

  #isCurrent(tabId, entry, token) {
    return this.tabs.get(tabId) === entry && entry.state.name === STATES.SEARCHING && entry.state.token === token;
  }

  async #settle(tabId, entry, token, listingUrl, event) {
    if (!this.#isCurrent(tabId, entry, token)) return "discarded";
    let currentUrl;
    try {
      currentUrl = await this.deps.getTabUrl(tabId);
    } catch {
      currentUrl = undefined;
    }
    if (!this.#isCurrent(tabId, entry, token)) return "discarded";
    if (currentUrl !== listingUrl) {
      // The tab moved to another page (or access to it was lost): never show this result there.
      this.tabs.delete(tabId);
      await this.#deliver(tabId, { type: "state", state: snapshot(INITIAL_STATE) });
      return "discarded";
    }
    entry.abort = null;
    const state = this.#setState(tabId, entry, event);
    await this.#deliver(tabId, { type: "state", state });
    return state.name;
  }

  async #deliver(tabId, message) {
    try {
      await this.deps.deliver(tabId, message);
    } catch {
      // Content script gone (tab navigated/closed); nothing to show.
    }
  }

  #activeDelta(d) {
    this.active += d;
    this.deps.onActiveCountChange(this.active);
  }
}
