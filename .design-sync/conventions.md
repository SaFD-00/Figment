# Figment design system — conventions

Figment is a light-blue, Inter-based SaaS UI for generating & editing scientific figures. Components are **React + Tailwind utility classes** — no CSS-in-JS, no exported class maps. The components carry their own styling; you build layout with standard Tailwind utilities plus the brand tokens below. Every component is reached at `window.Figment.<Name>` (bundle in the root `_ds_bundle.js`).

## Styling idiom — brand tokens

These Figment-specific utility classes all ship in the compiled stylesheet; use them for on-brand color/shape/elevation. Standard Tailwind utilities (flex, grid, gap-_, p-_, text-_, etc.) are available for layout.

| Concern | Utilities |
|---|---|
| Surfaces | `bg-bg` (app #f5f8ff) · `bg-panel` (#fff) · `bg-surface2` (#eef3fc) · `bg-accent` (#3b82f6) · `bg-accent-soft` (#eff6ff) |
| Text | `text-ink` (#0f1b35) · `text-ink-soft` (#3a4a6b) · `text-muted` (#7488a8) · `text-accent` (#3b82f6) · `text-accent-ink` (#1e40af) |
| Borders | `border-line` (#e2e9f5) · `border-line-strong` (#cdd9ee) |
| Focus ring | `ring-accent` (with `focus-visible:ring-2`) |
| Radius | `rounded-xl` (.875rem) · `rounded-2xl` (1.125rem) |
| Elevation | `shadow-card` (resting) · `shadow-soft` (raised / hover) |
| Type | `font-sans` (Inter — shipped as a variable woff2 in `fonts/`) |

Canonical surface: `<div className="rounded-2xl border border-line bg-panel p-6 shadow-card">…</div>`.

## Components & required context

- **Compose freely, no provider needed:** `Button` (variant `primary` | `secondary` | `ghost` | `danger`; size `sm` | `md` | `lg`), `Spinner` (inline, inherits `currentColor`), `FeatureGrid` (static 3-pillar section, no props).
- **Self-fetch from the backend** (`/api/...`) on mount: `ModelPill` / `ModelPillRow` (model catalog from `/api/models/all`) and `RecentProjects` (`/api/projects`). They render a loading/empty state until the backend responds.
- **Require the Next.js app-router:** `ProjectCard` renders a `next/link <Link>` and `PromptBox` calls `useRouter()` — they only render inside a Next.js app (or under an `AppRouterContext` provider). `ProjectCard` takes a `project` object prop.

> ⚠️ The bundle also exports `DesignSyncProvider`. It is a **preview-only harness** that mocks the router and seeds fake model/project data so cards render in isolation. **Do not use it in shipped designs** — it would inject mock data and a no-op router. (Ignore any per-component `.prompt.md` line that suggests wrapping in it.)

## Where the truth lives

Read the design system's `styles.css` (and the `tokens/tokens.css`, `fonts/fonts.css`, and `_ds_bundle.css` it `@import`s) for the full compiled utility set, and each component's `.d.ts` (props) + `.prompt.md` (usage) before composing. `tokens/tokens.css` also exposes the brand palette as CSS custom properties (`--color-accent`, `--color-ink`, `--color-bg`, `--radius-2xl`, `--shadow-card`, `--font-sans`, …) for raw-CSS use, and `guidelines/` holds the brand / layout / color-&-token / component-usage guides.

## Build snippet

```tsx
const { Button } = window.Figment;

<section className="rounded-2xl border border-line bg-panel p-6 shadow-card font-sans">
  <h3 className="text-lg font-bold text-ink">Generate a figure</h3>
  <p className="mt-1 text-sm text-muted">Describe it, then let Figment render it.</p>
  <div className="mt-4 flex gap-3">
    <Button variant="secondary">Enhance</Button>
    <Button variant="primary">Generate</Button>
  </div>
</section>
```
