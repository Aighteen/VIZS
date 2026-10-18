# spectrum

Local Photon Spectrum iMessage adapter for VIZS. `src/index.ts` (`npm start`)
is still the original echo agent. `src/test-bridge.mjs` is the bounded shopping
bridge that calls the Python API's `/api/v1/evaluate-message`. `src/launch.mjs`
(`npm run shop`) is the supported way to start the API and the bridge together. Do not log user numbers
or message contents. Credentials are in ignored `.env`.

Validated on Windows: `npm.cmd run typecheck`; `npm.cmd start` initialized Spectrum with one
iMessage provider. The bounded bridge completed a user-confirmed handset round trip
(before the launcher existed). Use `npm ci` (`npm.cmd ci` on Windows) for reproducible dependencies. Installation reported 18 moderate
dependency advisories; no forced updates applied.

## Environment

Copy `.env.example` to `.env` (ignored) and fill in:

- `PROJECT_ID`, `PROJECT_SECRET`: project Settings on the [Photon dashboard](https://app.photon.codes).
- `VIZS_REGISTERED_RECIPIENT`: the only sender whose direct messages the shopping bridge admits.

Process environment variables override `.env`. Launcher-only options:
`VIZS_PYTHON` (Python executable; default is the repo `.venv` python if present, else `python3` on
macOS/Linux or `py -3` on Windows), `VIZS_LAUNCH_PORT` (default 8787),
`VIZS_LAUNCH_HEALTH_TIMEOUT_MS` (default 30000), `VIZS_LAUNCH_LOCK` (lock file path; default
`vizs-photon-launcher.lock` in the OS temp dir).

## Bounded shopping launcher

| Command | What it does |
| --- | --- |
| `npm run shop:check` | Offline dry run: reports config presence (never values), starts the API offline, waits for `/healthz`, stops it. No Spectrum connection. Works without credentials. |
| `npm run shop` | Offline API (no provider credits) + bounded iMessage bridge. Real iMessage replies are sent. |
| `npm run shop -- --live` | Same, but the API may make paid Grok/Tavily calls. Only when authorized. |
| `npm test` | Bridge handler and launcher unit tests (no network). |

Add `-- --port 9000` to choose a port. On Windows use `npm.cmd` in PowerShell, for example
`npm.cmd run shop:check` and `npm.cmd run shop -- --live`.

What the launcher does:

1. Refuses before starting anything if `PROJECT_ID`, `PROJECT_SECRET`, `VIZS_REGISTERED_RECIPIENT`
   or the installed SDK are missing (exit 2), if another launcher holds the lock (exit 3), or if
   something already answers on the port (exit 3). A lock whose PID is no longer running is reclaimed.
2. Starts `python -m app.workflow.dev_server --port <port>` from the repo root on `127.0.0.1`,
   adding `--live` only when you pass `--live`. API output is suppressed (access log is off).
3. Waits for `/healthz` to report `status=ok`, `evaluation_ready=true` and the expected
   `provider_mode`; otherwise it stops the API (exit 1).
4. Runs `test-bridge.mjs` with `VIZS_LOCAL_API=http://127.0.0.1:<port>/api/v1/evaluate-message`
   and the credentials. Only the bridge's status lines (`READY`, `EVALUATION_STATUS`,
   `DELIVERY_STATUS`, `REPLY_*`, `BOUNDED_TEST_FINISHED`, `TEST_WINDOW_EXPIRED`, `BRIDGE_*`) are
   printed; other output is counted and suppressed.
5. When the bridge finishes (bounded test done or ten-minute expiry), the API dies, a 12-minute
   hard cap is reached, or you press Ctrl+C, it stops the other process (SIGTERM, then SIGKILL after
   5 s; `taskkill /T /F` on Windows) and removes the lock. Exit code: 0 bridge finished cleanly,
   1 failure, 130/143 on Ctrl+C/SIGTERM.

Limitation: if the launcher itself is killed with SIGKILL (or Task Manager), its children cannot
be cleaned up; check for a leftover `app.workflow.dev_server` / `test-bridge.mjs` process before relaunching.
Stale-lock detection is by PID only.

## Where to go next

- [Spectrum docs](https://photon.codes/docs/spectrum-ts)
- Add more providers from `spectrum-ts/providers/*`.
