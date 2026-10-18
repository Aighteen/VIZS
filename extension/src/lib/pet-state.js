// Pure pet state machine. There is deliberately no "reviewing sources" state or progress value:
// the backend returns one final response, so Searching covers the whole request.

export const STATES = Object.freeze({ IDLE: "idle", SEARCHING: "searching", FINISHED: "finished", ERROR: "error" });

export const INITIAL_STATE = Object.freeze({ name: STATES.IDLE, token: null, viewModel: null, error: null });

export function canStartRequest(state) {
  return state.name !== STATES.SEARCHING;
}

export function reduce(state, event) {
  switch (event.type) {
    case "CHECK":
      if (!canStartRequest(state)) return state; // duplicate click while searching: ignored
      return { name: STATES.SEARCHING, token: event.token, viewModel: null, error: null };
    case "RESULT":
      if (state.name !== STATES.SEARCHING || state.token !== event.token) return state; // stale
      return { name: STATES.FINISHED, token: event.token, viewModel: event.viewModel, error: null };
    case "FAIL":
      if (event.token == null) {
        // Pre-request failure (not paired, unsupported page, bad price): only when not searching.
        if (state.name === STATES.SEARCHING) return state;
        return { name: STATES.ERROR, token: null, viewModel: null, error: event.error };
      }
      if (state.name !== STATES.SEARCHING || state.token !== event.token) return state; // stale
      return { name: STATES.ERROR, token: event.token, viewModel: null, error: event.error };
    case "RESET":
      return INITIAL_STATE;
    default:
      return state;
  }
}

/** Snapshot safe to send to the content script (plain data only). */
export function snapshot(state) {
  return { name: state.name, token: state.token, viewModel: state.viewModel, error: state.error };
}
