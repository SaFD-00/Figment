# Figment — Layout & Spacing

## App shell

- Page background is always `bg-bg` (the light-blue tint `#f5f8ff`). Set it on the page root: `<main className="min-h-screen">` over the body's `bg-bg`. Never put content directly on white at full width — content sits on `bg-panel` surfaces floating over `bg-bg`.
- **Header:** sticky-feeling bar with `border-b border-line bg-panel/70 backdrop-blur`. The translucent panel + blur is the signature top chrome.
- **Centered column:** wrap content in `mx-auto max-w-6xl px-6` (header/wide) or `mx-auto max-w-5xl px-6 py-16` (main column). Hero/focused content narrows further to `max-w-2xl` / `max-w-xl`. Always horizontally center with `mx-auto`.

## The canonical surface

Every card, panel, and grouped section uses this exact recipe:

```tsx
<div className="rounded-2xl border border-line bg-panel p-6 shadow-card">…</div>
```

- `rounded-2xl` (1.125rem) is the default card radius; `rounded-xl` (0.875rem) for smaller controls (buttons, inputs, popovers); `rounded-full` for pills.
- `border border-line` on every surface — Figment surfaces are defined by a hairline border, not just shadow.
- `p-6` is the standard card padding; tighter chrome uses `p-3` (composer) and `p-3` card footers.

## Elevation

Two shadows, two meanings — do not invent others:

- `shadow-card` — **resting** elevation. The default for cards, feature tiles, project cards.
- `shadow-soft` — **raised / interactive**. Use for hover lift, popovers/menus, and the primary input the user acts in (the prompt composer rests at `shadow-soft` because it is the focal element).
- Idiomatic hover lift: `shadow-card transition-shadow hover:shadow-soft` (see project cards). Pair image hover with `group-hover:scale-[1.02]`.

## Spacing rhythm

- **Between major page sections:** large, generous gaps — `flex flex-col gap-20` in the main column.
- **Inside a card:** `mt-1` after a heading, `mt-4` before a list/action row, `space-y-3` for list items.
- **Action rows:** `flex items-center justify-between gap-3`, separated from content above with `border-t border-line pt-3`.
- **Grids:** responsive and centered. Feature trio `grid gap-6 md:grid-cols-3`; project gallery `grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5`.

## Do / Don't

- DO compose layout with standard Tailwind utilities (`flex`, `grid`, `gap-*`, `p-*`, `mx-auto`, `max-w-*`); only color/shape/elevation come from brand tokens.
- DO let surfaces breathe — generous `gap-20` between sections is on-brand, not wasteful.
- DON'T stack borderless white blocks; every surface gets `border border-line`.
- DON'T use ad-hoc shadows or radii outside `shadow-card`/`shadow-soft` and `rounded-xl`/`rounded-2xl`/`rounded-full`.
