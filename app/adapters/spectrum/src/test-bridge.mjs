// Bounded registered-recipient live test: clarification then one URL evaluation. Existing echo entry point unchanged.
import { Spectrum } from "spectrum-ts";
import { imessage } from "@spectrum-ts/imessage";
import { createBridgeHandler } from "./bridge-handler.mjs";
const log = console.log.bind(console);
for (const name of ["log", "info", "warn", "error", "debug"]) console[name] = () => {};
const recipient = process.env.VIZS_REGISTERED_RECIPIENT;
const api = process.env.VIZS_LOCAL_API;
if (!recipient || !api || !process.env.PROJECT_ID || !process.env.PROJECT_SECRET) throw new Error("Missing test configuration");
const target = new URL(api);
if (target.protocol !== "http:" || target.hostname !== "127.0.0.1" || target.pathname !== "/api/v1/evaluate-message") throw new Error("Loopback API required");
let app;
let closing = false;
async function close(reason) {
  if (closing) return;
  closing = true;
  log(reason);
  if (app) await app.stop();
}
// Launcher/terminal stop: close the Spectrum connection before exiting (second signal uses Node's default).
for (const signal of ["SIGINT", "SIGTERM"]) process.once(signal, () => { void close("BRIDGE_SIGNALLED").finally(() => process.exit(0)); });
const deadline = setTimeout(() => { void close("TEST_WINDOW_EXPIRED").finally(() => process.exit(0)); }, 600_000);
const handler = createBridgeHandler({recipient, onSendResult: async (space, sent) => {
  let latest = sent;
  for (let attempt=0; sent?.id && attempt<3 && !latest?.isDelivered; attempt++) {
    await new Promise(resolve=>setTimeout(resolve,1000));
    try { latest = await imessage(app).getMessage(space,sent.id) ?? latest; } catch { break; }
  }
  log("DELIVERY_STATUS:"+JSON.stringify({messageIdPresent:!!sent?.id,
    isSent:latest?.isSent??null, isDelivered:latest?.isDelivered??null,
    sendErrorCode:latest?.sendErrorCode??null, deliveredAt:latest?.dateDelivered??null}));
}, evaluate: async (payload) => {
  const response = await fetch(api, {method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify(payload), signal:AbortSignal.timeout(110000), redirect:"error"});
  if (!response.ok) throw new Error("Evaluation unavailable");
  const result = await response.json();
  log("EVALUATION_STATUS:"+JSON.stringify({decision:result.assessment?.decision??null,
    dataMode:result.assessment?.data_mode??null, evidenceCount:result.assessment?.evidence?.length??null,
    research:result.assessment?.research??[],
    unavailable:/unavailable/i.test(result.assessment?.summary??""),
    timedOut:/timed out/i.test(result.assessment?.summary??""),
    invalidOutput:/could not safely read/i.test(result.assessment?.summary??"")}));
  return result;
}});
try {
  app = await Spectrum({projectId:process.env.PROJECT_ID, projectSecret:process.env.PROJECT_SECRET, providers:[imessage.config()]});
  log("READY: registered-recipient iMessage test; up to two clarification messages then one URL evaluation; ten-minute expiry.");
  for await (const [space,message] of app.messages) {
    try {
      const result = await handler.handle(space,message);
      if (result !== "ignored") log("REPLY_REQUEST_COMPLETED: handset receipt unconfirmed.");
    } catch { log("REPLY_FAILED: no automatic retry."); }
    if (handler.exhausted) { await close("BOUNDED_TEST_FINISHED"); break; }
  }
} catch { log("BRIDGE_FAILED: details omitted for privacy."); process.exitCode=1; }
finally { clearTimeout(deadline); await close("BRIDGE_STOPPED"); }
