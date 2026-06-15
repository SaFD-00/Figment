// Static feature showcase mirroring Figment's three pillars (Generate / Edit / Vectorize).

interface Pillar {
  title: string;
  tagline: string;
  items: { name: string; desc: string }[];
}

const PILLARS: Pillar[] = [
  {
    title: "Generate",
    tagline: "Turn ideas into figures instantly",
    items: [
      { name: "Text-to-Figure", desc: "Generate schematics from text or PDFs." },
      { name: "Image-to-Figure", desc: "Convert sketches or photos into illustrations." },
      { name: "Reference-to-Figure", desc: "Match the style and layout of any reference." },
    ],
  },
  {
    title: "Edit",
    tagline: "Refine without starting over",
    items: [
      { name: "Text Edit", desc: "Fix labels or legends directly on the image." },
      { name: "Region Redraw", desc: "Redraw only the specific parts you select." },
      { name: "BG Remove", desc: "Remove backgrounds for a clean white canvas." },
    ],
  },
  {
    title: "Vectorize",
    tagline: "Export to fully editable formats",
    items: [
      { name: "Editable PPTX", desc: "Export directly to slides for native editing." },
      { name: "SVG", desc: "Download scalable vectors for design tools." },
      { name: "Built-in Canvas", desc: "Open in our canvas for raster & vector edits." },
    ],
  },
];

export function FeatureGrid() {
  return (
    <section id="features" className="w-full">
      <div className="grid gap-6 md:grid-cols-3">
        {PILLARS.map((p) => (
          <div
            key={p.title}
            className="rounded-2xl border border-line bg-panel p-6 shadow-card"
          >
            <h3 className="text-lg font-bold text-ink">{p.title}</h3>
            <p className="mt-1 text-sm font-medium text-accent-ink">{p.tagline}</p>
            <ul className="mt-4 space-y-3">
              {p.items.map((it) => (
                <li key={it.name}>
                  <p className="text-sm font-semibold text-ink">{it.name}</p>
                  <p className="text-sm text-muted">{it.desc}</p>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}
