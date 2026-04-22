/**
 * 解析 FastAPI SSE：`data: {...}\\n\\n`，支持半包（跨 chunk 拼接）。
 */
export type SseJsonEvent =
  | { type: "token"; content: string }
  | { type: "metadata"; confidence: number; sources: string[] }
  | { type: "workflow_event"; node: string; updated_keys: string[] }
  | { type: "done" }
  | { type: "error"; message: string };

export function parseSseDataLines(buffer: string): { events: SseJsonEvent[]; rest: string } {
  const events: SseJsonEvent[] = [];
  let rest = buffer;

  while (true) {
    const idx = rest.indexOf("\n\n");
    if (idx === -1) break;
    const rawBlock = rest.slice(0, idx);
    rest = rest.slice(idx + 2);

    const lines = rawBlock.split("\n").map((l) => l.trimEnd());
    for (const line of lines) {
      if (!line.startsWith("data:")) continue;
      const payload = line.slice("data:".length).trim();
      if (payload === "[DONE]") {
        events.push({ type: "done" });
        continue;
      }
      try {
        const obj = JSON.parse(payload) as SseJsonEvent;
        events.push(obj);
      } catch {
        // ignore malformed line
      }
    }
  }

  return { events, rest };
}
