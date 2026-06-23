// design-sync build-only Tailwind config. Reuses the app's design tokens
// (theme.extend) but widens `content` to include the design-sync preview
// harness + authored previews so their utility classes are compiled into the
// shipped stylesheet (cfg.cssEntry → _ds_bundle.css). Not used by the app.
import type { Config } from "tailwindcss";
import base from "./tailwind.config";

const config: Config = {
  ...base,
  content: [
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
    "./.design-sync-entry.tsx",
    "../.design-sync/previews/**/*.{ts,tsx}",
  ],
  // The design agent only receives the COMPILED stylesheet (no Tailwind at
  // build time), so ship the full brand-token palette even where the 8 synced
  // components don't use a given utility — the agent styles on-brand from these.
  safelist: [
    {
      pattern:
        /^(bg|text|border|ring)-(bg|panel|surface2|ink|ink-soft|muted|line|line-strong|accent|accent-ink|accent-soft)$/,
    },
    { pattern: /^rounded-(xl|2xl)$/ },
    { pattern: /^shadow-(card|soft)$/ },
    "font-sans",
  ],
};

export default config;
