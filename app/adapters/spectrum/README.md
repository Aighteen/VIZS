# spectrum

Local Photon Spectrum iMessage connection-test adapter for VIZS. This agent
echoes text using the official scaffold's `app.messages` / `space.send` interface;
it is not yet connected to the Python shopping workflow. Do not log user numbers
or message contents. Credentials are in ignored `.env`; start scripts explicitly
load it using Node's `--env-file` support (tested on Node 24.14.0).

Validated: `npm.cmd run typecheck`; `npm.cmd start` initialized Spectrum with one
iMessage provider and remained running. Actual handset round trip awaits test.
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
