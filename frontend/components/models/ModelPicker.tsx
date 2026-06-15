"use client";

import { useEffect } from "react";
import { useModelsStore } from "../../lib/models";
import { isCloud, type Model } from "../../lib/types";

function notReadyHint(m: Model): string {
  if (m.ready) return "";
  return isCloud(m) ? " — add API key" : " — not downloaded";
}

/**
 * A single dropdown bound to the unified models store, grouped Local / Cloud.
 * `kind` selects which catalog (image-generation or chat/planner LLM) it controls.
 */
export function ModelSelect({
  kind,
  className,
  allowNotReady = false,
}: {
  kind: "image" | "llm";
  className?: string;
  allowNotReady?: boolean;
}) {
  const {
    image,
    llm,
    load,
    selectedImageId,
    selectedLlmId,
    setImageModel,
    setLlmModel,
  } = useModelsStore();

  useEffect(() => {
    void load();
  }, [load]);

  const models = kind === "image" ? image : llm;
  const value = (kind === "image" ? selectedImageId : selectedLlmId) ?? "";
  const onChange = kind === "image" ? setImageModel : setLlmModel;

  const local = models.filter((m) => !isCloud(m));
  const cloud = models.filter((m) => isCloud(m));

  const renderOpt = (m: Model) => (
    <option key={m.id} value={m.id} disabled={!allowNotReady && !m.ready}>
      {m.label}
      {notReadyHint(m)}
    </option>
  );

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={
        className ??
        "rounded-lg border border-line bg-white px-2.5 py-1.5 text-sm text-ink focus:border-accent focus:outline-none"
      }
    >
      {models.length === 0 && <option value="">Loading…</option>}
      {local.length > 0 && (
        <optgroup label="Local">{local.map(renderOpt)}</optgroup>
      )}
      {cloud.length > 0 && (
        <optgroup label="Cloud">{cloud.map(renderOpt)}</optgroup>
      )}
    </select>
  );
}

/** Labeled image + LLM pickers side by side — used in composers/toolbars. */
export function ModelPickerRow({ className }: { className?: string }) {
  return (
    <div className={className ?? "flex flex-wrap items-center gap-3"}>
      <label className="flex items-center gap-2 text-sm text-muted">
        <span className="hidden sm:inline">Image</span>
        <ModelSelect kind="image" />
      </label>
      <label className="flex items-center gap-2 text-sm text-muted">
        <span className="hidden sm:inline">LLM</span>
        <ModelSelect kind="llm" />
      </label>
    </div>
  );
}
