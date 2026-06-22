// SSE helpers.
// - streamChat: POST /chat returns text/event-stream. Native EventSource cannot
//   POST, so we read the ReadableStream and parse `event:` / `data:` lines.
// - jobEvents: GET /jobs/{id}/events is a plain GET, so native EventSource works.

import type { GenSpec } from "./types";

const BASE = "/api";

// ---------------------------------------------------------------------------
// Chat streaming (POST + ReadableStream parser)
// ---------------------------------------------------------------------------

export interface ChatHandlers {
  onDelta?: (text: string) => void;
  onGenSpec?: (spec: GenSpec) => void;
  onGenSpecError?: (err: { error: string; raw?: string }) => void;
  onDone?: () => void;
  onError?: (err: { error: string }) => void;
}

export interface ChatStreamControl {
  // Abort the in-flight request.
  cancel: () => void;
  // Resolves when the stream finishes (done/error/abort).
  done: Promise<void>;
}

interface SSEEvent {
  event: string;
  data: string;
}

// Parse a chunk of accumulated SSE text into complete events.
// Returns [events, remainder] where remainder is the trailing partial block.
function parseSSE(buffer: string): [SSEEvent[], string] {
  const events: SSEEvent[] = [];
  // Events are separated by a blank line. Normalize CRLF.
  const normalized = buffer.replace(/\r\n/g, "\n");
  const blocks = normalized.split("\n\n");
  // The last element may be an incomplete block -> keep as remainder.
  const remainder = blocks.pop() ?? "";

  for (const block of blocks) {
    if (!block.trim()) continue;
    let eventName = "message";
    const dataLines: string[] = [];
    for (const rawLine of block.split("\n")) {
      const line = rawLine;
      if (line.startsWith(":")) continue; // comment / heartbeat
      if (line.startsWith("event:")) {
        eventName = line.slice("event:".length).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice("data:".length).replace(/^ /, ""));
      }
    }
    events.push({ event: eventName, data: dataLines.join("\n") });
  }
  return [events, remainder];
}

export interface ChatAttachment {
  asset: string;
  hint?: "source" | "reference";
}

export function streamChat(
  projectId: string,
  message: string,
  handlers: ChatHandlers,
  opts?: { llmModel?: string | null; attachments?: ChatAttachment[] },
): ChatStreamControl {
  const controller = new AbortController();

  const done = (async () => {
    try {
      const res = await fetch(`${BASE}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          project_id: projectId,
          message,
          llm_model: opts?.llmModel ?? null,
          attachments: opts?.attachments ?? null,
        }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        handlers.onError?.({
          error: `Chat request failed: ${res.status} ${res.statusText}`,
        });
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done: streamDone } = await reader.read();
        if (streamDone) break;
        buffer += decoder.decode(value, { stream: true });
        const [events, remainder] = parseSSE(buffer);
        buffer = remainder;
        for (const ev of events) {
          dispatchChatEvent(ev, handlers);
        }
      }

      // Flush any trailing complete block.
      buffer += decoder.decode();
      if (buffer.trim()) {
        const [events] = parseSSE(buffer + "\n\n");
        for (const ev of events) dispatchChatEvent(ev, handlers);
      }
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return;
      handlers.onError?.({ error: (err as Error)?.message ?? "stream error" });
    }
  })();

  return {
    cancel: () => controller.abort(),
    done,
  };
}

function dispatchChatEvent(ev: SSEEvent, handlers: ChatHandlers) {
  switch (ev.event) {
    case "delta": {
      try {
        const parsed = JSON.parse(ev.data) as { text: string };
        handlers.onDelta?.(parsed.text ?? "");
      } catch {
        handlers.onDelta?.(ev.data);
      }
      break;
    }
    case "genspec": {
      try {
        handlers.onGenSpec?.(JSON.parse(ev.data) as GenSpec);
      } catch (e) {
        handlers.onGenSpecError?.({
          error: (e as Error)?.message ?? "bad genspec",
          raw: ev.data,
        });
      }
      break;
    }
    case "genspec_error": {
      try {
        handlers.onGenSpecError?.(
          JSON.parse(ev.data) as { error: string; raw?: string },
        );
      } catch {
        handlers.onGenSpecError?.({ error: ev.data });
      }
      break;
    }
    case "done":
      handlers.onDone?.();
      break;
    case "error": {
      try {
        handlers.onError?.(JSON.parse(ev.data) as { error: string });
      } catch {
        handlers.onError?.({ error: ev.data });
      }
      break;
    }
    default:
      break;
  }
}

// ---------------------------------------------------------------------------
// Job events (GET + native EventSource)
// ---------------------------------------------------------------------------

export interface JobProgress {
  progress: number; // 0..1
  step?: number;
  total?: number;
  node?: string;
  job_id?: string;
}

export interface JobDone {
  result_asset: string;
  progress?: number;
}

export interface JobHandlers {
  onQueued?: () => void;
  onProgress?: (p: JobProgress) => void;
  onPreview?: (previewB64: string) => void;
  onDone?: (d: JobDone) => void;
  onError?: (err: { message: string }) => void;
}

export interface JobEventControl {
  close: () => void;
}

export function jobEvents(jobId: string, handlers: JobHandlers): JobEventControl {
  const es = new EventSource(`${BASE}/jobs/${jobId}/events`);
  let closed = false;
  const close = () => {
    if (!closed) {
      closed = true;
      es.close();
    }
  };

  es.addEventListener("queued", () => handlers.onQueued?.());

  es.addEventListener("progress", (e) => {
    try {
      handlers.onProgress?.(JSON.parse((e as MessageEvent).data) as JobProgress);
    } catch {
      /* ignore malformed */
    }
  });

  es.addEventListener("preview", (e) => {
    try {
      const d = JSON.parse((e as MessageEvent).data) as { preview_b64: string };
      handlers.onPreview?.(d.preview_b64);
    } catch {
      /* ignore */
    }
  });

  es.addEventListener("done", (e) => {
    try {
      handlers.onDone?.(JSON.parse((e as MessageEvent).data) as JobDone);
    } catch {
      /* ignore */
    } finally {
      close();
    }
  });

  es.addEventListener("error", (e) => {
    // EventSource fires a generic `error` event on network failure too.
    const data = (e as MessageEvent).data;
    if (typeof data === "string" && data) {
      try {
        handlers.onError?.(JSON.parse(data) as { message: string });
      } catch {
        handlers.onError?.({ message: data });
      }
      close();
    } else if (es.readyState === EventSource.CLOSED) {
      handlers.onError?.({ message: "connection closed" });
      close();
    }
  });

  return { close };
}
