"use client";

export type HomeMode = "generate" | "edit" | "reference" | "figure";

const TABS: { id: HomeMode; label: string }[] = [
  { id: "generate", label: "Generate" },
  { id: "edit", label: "Edit / Upload" },
  { id: "reference", label: "Reference" },
  { id: "figure", label: "Figure" },
];

export function ModeTabs({
  mode,
  onChange,
}: {
  mode: HomeMode;
  onChange: (m: HomeMode) => void;
}) {
  return (
    <div className="inline-flex items-center gap-1 rounded-full border border-line bg-white p-1 shadow-card">
      {TABS.map((t) => {
        const active = t.id === mode;
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
              active
                ? "bg-accent text-white"
                : "text-muted hover:text-ink hover:bg-zinc-100"
            }`}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
