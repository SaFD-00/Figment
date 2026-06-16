"use client";

import { useEffect, useRef, useState } from "react";
import { useModelsStore } from "../../lib/models";
import { isCloud, type GenMode, type Model } from "../../lib/types";

// "Qwen-Image 2512 (local · quality txt2img)" -> "Qwen-Image 2512"
function shortLabel(label: string): string {
  const i = label.indexOf(" (");
  return i === -1 ? label : label.slice(0, i);
}

function notReadyHint(m: Model): string {
  if (m.ready) return "";
  return isCloud(m) ? "add API key" : "not downloaded";
}

function KindIcon({ kind }: { kind: "image" | "llm" }) {
  // image = picture frame, llm = chat bubble. Subtle leading glyph in the pill.
  return kind === "image" ? (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 shrink-0" fill="none" aria-hidden>
      <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="8.5" cy="9.5" r="1.6" fill="currentColor" />
      <path d="M5 18l4.5-4.5 3 3L17 11l4 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 shrink-0" fill="none" aria-hidden>
      <path d="M4 5h16v11H9l-4 3v-3H4z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

function EngineBadge({ cloud }: { cloud: boolean }) {
  return (
    <span
      className={`shrink-0 rounded px-1 py-0.5 text-[10px] font-medium leading-none ${
        cloud ? "bg-accent-soft text-accent" : "bg-zinc-100 text-muted"
      }`}
    >
      {cloud ? "Cloud" : "Local"}
    </span>
  );
}

function Chevron() {
  return (
    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 shrink-0 text-muted" fill="none" aria-hidden>
      <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * figurelabs-style inline model pill bound to the unified models store.
 * A compact button shows the selected model; clicking opens a grouped Local/Cloud popover.
 * `kind` selects the catalog (image-generation or chat/planner LLM).
 * For `kind="image"`, `mode` scopes both the list (mode-compatible models only) and the
 * selection (each generation mode remembers its own image model). Defaults to "txt2img".
 */
export function ModelPill({
  kind,
  mode,
  placement = "bottom",
  allowNotReady = false,
}: {
  kind: "image" | "llm";
  mode?: GenMode;
  placement?: "top" | "bottom";
  allowNotReady?: boolean;
}) {
  const {
    image,
    llm,
    load,
    selectedLlmId,
    setImageModel,
    setLlmModel,
    getImageModelForMode,
  } = useModelsStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void load();
  }, [load]);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const imageMode: GenMode = mode ?? "txt2img";
  const models =
    kind === "image" ? image.filter((m) => m.modes.includes(imageMode)) : llm;
  const selectedId =
    kind === "image" ? getImageModelForMode(imageMode) : selectedLlmId;
  const selected = models.find((m) => m.id === selectedId) ?? null;

  const local = models.filter((m) => !isCloud(m));
  const cloud = models.filter((m) => isCloud(m));

  function choose(m: Model) {
    if (!allowNotReady && !m.ready) return;
    if (kind === "image") setImageModel(imageMode, m.id);
    else setLlmModel(m.id);
    setOpen(false);
  }

  const renderGroup = (title: string, list: Model[]) =>
    list.length > 0 && (
      <div className="py-1">
        <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted">
          {title}
        </p>
        {list.map((m) => {
          const disabled = !allowNotReady && !m.ready;
          const active = m.id === selectedId;
          return (
            <button
              key={m.id}
              type="button"
              onClick={() => choose(m)}
              disabled={disabled}
              title={m.label}
              className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm transition-colors ${
                disabled
                  ? "cursor-not-allowed text-muted/60"
                  : active
                    ? "bg-accent-soft text-accent"
                    : "text-ink hover:bg-zinc-50"
              }`}
            >
              <span className="w-3.5 shrink-0 text-accent">{active ? "✓" : ""}</span>
              <span className="flex-1 truncate">{shortLabel(m.label)}</span>
              {!m.ready && (
                <span className="shrink-0 text-[10px] text-muted">{notReadyHint(m)}</span>
              )}
            </button>
          );
        })}
      </div>
    );

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={selected?.label ?? "Select a model"}
        className="flex max-w-[220px] items-center gap-1.5 rounded-full border border-line bg-white px-2.5 py-1 text-sm text-ink transition-colors hover:border-accent"
      >
        <span className="text-muted">
          <KindIcon kind={kind} />
        </span>
        <span className="truncate font-medium">
          {selected ? shortLabel(selected.label) : "Loading…"}
        </span>
        {selected && <EngineBadge cloud={isCloud(selected)} />}
        <Chevron />
      </button>

      {open && (
        <div
          className={`absolute z-50 max-h-72 w-64 overflow-auto rounded-xl border border-line bg-white py-1 shadow-soft ${
            placement === "top" ? "bottom-full mb-1" : "top-full mt-1"
          }`}
        >
          {models.length === 0 && (
            <p className="px-3 py-2 text-sm text-muted">Loading…</p>
          )}
          {renderGroup("Local", local)}
          {renderGroup("Cloud", cloud)}
        </div>
      )}
    </div>
  );
}

/** Image + LLM pills side by side — used in the composer toolbars.
 * `mode` scopes the image pill to a generation mode (per-mode model selection). */
export function ModelPillRow({
  className,
  mode,
  placement = "bottom",
}: {
  className?: string;
  mode?: GenMode;
  placement?: "top" | "bottom";
}) {
  return (
    <div className={className ?? "flex flex-wrap items-center gap-2"}>
      <ModelPill kind="image" mode={mode} placement={placement} />
      <ModelPill kind="llm" placement={placement} />
    </div>
  );
}
