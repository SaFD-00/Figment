# Figment — Component Usage

Every Figment component is reached at **`window.Figment.<Name>`** (the bundle is the root `_ds_bundle.js`). Components are React + Tailwind — they carry their own styling; you only add layout with standard utilities and brand tokens. Read each component's `.d.ts` (props) and `.prompt.md` (usage) before composing.

```tsx
const { Button, Spinner, FeatureGrid, ProjectCard, PromptBox, ModelPill, ModelPillRow } = window.Figment;
```

## Compose freely — no context required

- **`Button`** — `variant`: `"primary" | "secondary" | "ghost" | "danger"` (default `secondary`); `size`: `"sm" | "md" | "lg"` (default `md`). Forwards all native button props. `primary` = `bg-accent` fill; `secondary` = white + `border-line`; `ghost` = transparent; `danger` = white + red text. Keep **one `primary` per surface**.
- **`Spinner`** — tiny inline spinner that inherits `currentColor`. **Button loading states only** — drop it inside a `Button` before the label (e.g. `{busy && <Spinner />}{busy ? "Starting…" : "Generate"}`). For job/progress, use a determinate progress UI, not this.
- **`FeatureGrid`** — static three-pillar marketing section (Generate / Edit / Vectorize). No props; renders its own `md:grid-cols-3` of canonical cards.

## Self-fetch from the backend (`/api/…`) on mount

These call the backend themselves and render their own loading/empty states — just drop them in, no props needed for data:

- **`ModelPill`** — inline model selector pill. Props: `kind: "image" | "llm"` (required), `mode?` (scopes image models to a generation mode + remembers per-mode selection), `placement?: "top" | "bottom"`. Loads the catalog from `/api/models/all`.
- **`ModelPillRow`** — image + LLM pills side by side for composer toolbars (`mode?`, `placement?`, `className?`).
- **`RecentProjects`** — fetches `/api/projects`; renders the project gallery grid, or a quiet empty state, or nothing while loading.

```tsx
// A composer toolbar footer
<div className="flex items-center justify-between gap-3 border-t border-line px-2 pt-3">
  <ModelPillRow mode="txt2img" />
  <Button variant="primary">Generate</Button>
</div>
```

## Require the Next.js app-router

These only render inside a Next.js app (or under an `AppRouterContext`):

- **`ProjectCard`** — renders a `next/link <Link>`. Requires a `project` object prop (`{ id, title, cover_asset, updated_at, … }`). Use it inside `RecentProjects`, or map your own grid of them.
- **`PromptBox`** — the home prompt composer; calls `useRouter()` to hand off to the editor. No props.

If you are composing a page outside a Next.js router, prefer the self-fetching components or `Button`/`FeatureGrid`; do not reach for `ProjectCard`/`PromptBox`.

## ⚠️ DesignSyncProvider — preview only

The bundle also exports **`DesignSyncProvider`**. It is a **preview-only mock harness** that fakes the router and seeds fake model/project data so router-bound components render in isolation in the preview.

- **Never wrap shipped designs in `DesignSyncProvider`.** In a real app it injects mock data and a no-op router, breaking navigation and showing fake content.
- Ignore any per-component `.prompt.md` line that suggests wrapping in it — that guidance is for the isolated preview only.

## Do / Don't

- DO compose from `window.Figment.<Name>` and let self-fetching components manage their own data/loading.
- DO put `Spinner` only inside buttons; reach for `Button variant="danger"` for destructive actions.
- DON'T pass mock data through `DesignSyncProvider` in anything you ship.
- DON'T use `ProjectCard`/`PromptBox` outside a Next.js app-router context.
