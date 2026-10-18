# spectrum

Local Photon Spectrum iMessage adapter for VIZS. `src/index.ts` (`npm start`)
is still the original echo agent. `src/test-bridge.mjs` is the bounded shopping
bridge that calls the Python API's `/api/v1/evaluate-message`; see the root README
for its environment variables and limits. Do not log user numbers
or message contents. Credentials are in ignored `.env`; start scripts explicitly
load it using Node's `--env-file` support (tested on Node 24.14.0).

Validated on Windows: `npm.cmd run typecheck`; `npm.cmd start` initialized Spectrum with one
iMessage provider. The bounded bridge completed a user-confirmed handset round trip.
`node --test src/bridge-handler.test.mjs` last recorded 4 passed.
Use `npm.cmd ci` for reproducible dependencies. Installation reported 18 moderate
dependency advisories; no forced updates applied.

A [Spectrum](https://photon.codes/docs/spectrum-ts) project. Wired with: imessage.

## Environment

Before running, open `.env` and fill in the values:

From your project Settings on the [Photon dashboard](https://app.photon.codes):

- `PROJECT_ID`
- `PROJECT_SECRET`

## Run

```sh
npm install
npm run start
```

## Where to go next

- [Spectrum docs](https://photon.codes/docs/spectrum-ts)
- Edit `src/index.ts` to replace the echo loop with real agent logic.
- Add more providers from `spectrum-ts/providers/*`.
