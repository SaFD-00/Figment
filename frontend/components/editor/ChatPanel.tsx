"use client";

// Left chat panel.
// - Loads existing messages on mount.
// - Streams chat responses (POST /chat SSE) and appends assistant delta live.
// - When a `genspec` event arrives, shows a highlighted "Generate this" button
//   with editable seed + steps.
// - In mask mode, the input becomes a "Generate redraw" affordance handled by
//   the parent via onRedraw (the same input box is reused).

import { useEffect, useRef, useState } from "react";
import { assetFileUrl, getMessages } from "../../lib/api";
import { streamChat } from "../../lib/sse";
import { useEditorStore } from "../../lib/store";
import { useJobRunner } from "../../lib/useJob";
import type { ChatMessage, GenSpec } from "../../lib/types";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/Spinner";

interface Props {
  projectId: string;
  // Called when the user submits while in mask (redraw) mode.
  onRedraw: (prompt: string) => void;
}

export function ChatPanel({ projectId, onRedraw }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [assistantDraft, setAssistantDraft] = useState("");
  const [pendingError, setPendingError] = useState<string | null>(null);

  const maskMode = useEditorStore((s) => s.maskMode);
  const chatGenSpec = useEditorStore((s) => s.chatGenSpec);
  const setChatGenSpec = useEditorStore((s) => s.setChatGenSpec);
  const activeJob = useEditorStore((s) => s.activeJob);
  const { run } = useJobRunner();

  // Editable overrides for the genspec generate button.
  const [seed, setSeed] = useState<string>("");
  const [steps, setSteps] = useState<string>("");

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    getMessages(projectId)
      .then((m) => {
        if (alive) setMessages(m);
      })
      .catch(() => {
        /* none yet */
      });
    return () => {
      alive = false;
    };
  }, [projectId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, assistantDraft]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;

    // In mask mode, the input drives a region redraw instead of chat.
    if (maskMode) {
      onRedraw(text);
      setInput("");
      return;
    }

    if (streaming) return;
    setPendingError(null);
    setChatGenSpec(null);

    // Optimistically add the user's message.
    const userMsg: ChatMessage = {
      id: `local-${Date.now()}`,
      project_id: projectId,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setStreaming(true);
    setAssistantDraft("");

    let acc = "";
    streamChat(projectId, text, {
      onDelta: (t) => {
        acc += t;
        setAssistantDraft(acc);
      },
      onGenSpec: (spec) => {
        setChatGenSpec(spec);
        setSeed(spec.seed != null ? String(spec.seed) : "");
        setSteps(spec.steps != null ? String(spec.steps) : "");
      },
      onGenSpecError: (err) => {
        setPendingError(err.error || "Could not build a generation spec.");
      },
      onDone: () => {
        setStreaming(false);
        setMessages((m) => [
          ...m,
          {
            id: `local-a-${Date.now()}`,
            project_id: projectId,
            role: "assistant",
            content: acc,
            created_at: new Date().toISOString(),
          },
        ]);
        setAssistantDraft("");
      },
      onError: (err) => {
        setStreaming(false);
        setPendingError(err.error);
        setAssistantDraft("");
      },
    });
  }

  async function handleGenerateFromSpec() {
    if (!chatGenSpec) return;
    const spec: GenSpec = {
      ...chatGenSpec,
      seed: seed.trim() === "" ? null : Number(seed),
      steps: steps.trim() === "" ? null : Number(steps),
    };
    try {
      setChatGenSpec(null);
      await run(projectId, spec, { pushUndo: true });
    } catch (e) {
      setPendingError((e as Error)?.message ?? "Failed to start job.");
    }
  }

  const jobRunning =
    activeJob?.status === "running" || activeJob?.status === "queued";

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold text-ink">Chat</h2>
        <p className="text-xs text-muted">
          Describe a change, or ask for a new image.
        </p>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && !assistantDraft && (
          <p className="py-8 text-center text-xs text-muted">
            No messages yet.
          </p>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        {assistantDraft && (
          <MessageBubble
            message={{
              id: "draft",
              project_id: projectId,
              role: "assistant",
              content: assistantDraft,
              created_at: new Date().toISOString(),
            }}
          />
        )}
      </div>

      {/* GenSpec generate affordance */}
      {chatGenSpec && !maskMode && (
        <div className="mx-4 mb-2 rounded-xl border border-accent/40 bg-accent-soft p-3">
          <div className="mb-2 flex items-center gap-3">
            <span className="text-sm font-medium text-accent">
              ✨ Ready to generate
            </span>
          </div>
          <div className="mb-3 flex items-center gap-3 text-xs text-ink">
            <label className="flex items-center gap-1">
              Seed
              <input
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                placeholder="random"
                inputMode="numeric"
                className="w-24 rounded-md border border-line bg-white px-2 py-1 text-xs focus:border-accent focus:outline-none"
              />
            </label>
            <label className="flex items-center gap-1">
              Steps
              <input
                value={steps}
                onChange={(e) => setSteps(e.target.value)}
                placeholder="auto"
                inputMode="numeric"
                className="w-20 rounded-md border border-line bg-white px-2 py-1 text-xs focus:border-accent focus:outline-none"
              />
            </label>
          </div>
          <Button
            variant="primary"
            size="sm"
            className="w-full"
            onClick={() => void handleGenerateFromSpec()}
            disabled={jobRunning}
          >
            Generate this
          </Button>
        </div>
      )}

      {pendingError && (
        <p className="mx-4 mb-2 text-xs text-red-600">{pendingError}</p>
      )}

      <form
        onSubmit={handleSubmit}
        className="border-t border-line p-3"
      >
        {maskMode && (
          <p className="mb-2 text-xs font-medium text-accent">
            Mask mode — type a prompt and press Generate redraw.
          </p>
        )}
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
            rows={2}
            placeholder={
              maskMode
                ? "What should fill the masked area?"
                : "Message…"
            }
            className="flex-1 resize-none rounded-xl border border-line bg-white px-3 py-2 text-sm focus:border-accent focus:outline-none"
          />
          <Button
            type="submit"
            variant="primary"
            size="md"
            disabled={streaming || !input.trim()}
          >
            {streaming && <Spinner />}
            {maskMode ? "Redraw" : "Send"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const resultAsset = message.result_asset;
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
          isUser
            ? "bg-accent text-white"
            : "border border-line bg-white text-ink"
        }`}
      >
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
        {resultAsset && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={assetFileUrl(resultAsset)}
            alt="result"
            className="mt-2 w-32 rounded-lg border border-line"
          />
        )}
      </div>
    </div>
  );
}
