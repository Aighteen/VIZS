import { Spectrum } from "spectrum-ts";
import { imessage } from "@spectrum-ts/imessage";
// Spectrum bridges a single agent loop to many messaging interfaces.
// Each provider in `providers` adds an interface (terminal TUI, iMessage, …).
// Docs: https://photon.codes/docs/spectrum-ts
if (!process.env.PROJECT_ID || !process.env.PROJECT_SECRET) {
  console.error("Photon configuration missing PROJECT_ID or PROJECT_SECRET.");
  process.exit(1);
}

try {
const app = await Spectrum({
  projectId: process.env.PROJECT_ID!,
  projectSecret: process.env.PROJECT_SECRET!,
  providers: [
    // imessage
    imessage.config(),
  ],
});
console.log("Photon Spectrum initialized; iMessage handler waiting for inbound events.");

// `app.messages` is an async iterable. Each tick yields a `space` (the
// conversation) and an inbound `message`. Reply by awaiting `space.send(...)`.
for await (const [space, message] of app.messages) {
  if (message?.content?.type === "text" && typeof message.content.text === "string") {
    console.log("Inbound text received; content and sender omitted.");
    try {
      await space.send(`Photon Spectrum is connected. You said: ${message.content.text.slice(0, 1000)}`);
      console.log("Reply request completed; handset delivery is not yet confirmed.");
    } catch {
      console.error("Reply failed; no automatic retry of an ambiguous send.");
    }
  }
}
} catch {
  console.error("Photon startup or event stream failed. Check connection and account configuration.");
  process.exitCode = 1;
}
