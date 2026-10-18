import { randomUUID } from "node:crypto";

export function createBridgeHandler({ recipient, evaluate, maxMessages = 3, onSendResult = async () => {} }) {
  if (!recipient || !Number.isInteger(maxMessages) || maxMessages < 1 || maxMessages > 3) throw new Error("Invalid bounded test configuration");
  const seen = new Set();
  let handled = 0;
  let evaluations = 0;
  return {
    get exhausted() { return handled >= maxMessages || evaluations >= 1; },
    async handle(space, message) {
      if (handled >= maxMessages || evaluations >= 1 || space?.type !== "dm" || message?.direction !== "inbound" ||
          message?.sender?.id !== recipient || message?.content?.type !== "text" ||
          typeof message.content.text !== "string" || !message.content.text.trim() ||
          message.content.text.length > 4000 || typeof message.id !== "string" ||
          !message.id || seen.has(message.id)) return "ignored";
      seen.add(message.id); handled += 1;
      if (/https?:\/\//i.test(message.content.text)) evaluations += 1;
      let body;
      try {
        const result = await evaluate({ request_id: randomUUID(), message_text: message.content.text, channel: "debug" });
        if (typeof result?.message_text !== "string" || result.message_text.length > 2000) throw new Error("Invalid API response");
        body = result.message_text;
      } catch {
        body = "Shopping evaluation is unavailable or timed out. No seller conclusion was established. Please try again later.";
      }
      // Reserve before awaits; never retry an ambiguous send or issue a second reply.
      const sent = await space.send(body);
      await onSendResult(space, sent);
      return "send_request_completed";
    }
  };
}
