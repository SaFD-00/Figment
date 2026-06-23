# Figment — Color & Tokens

All brand utilities below **ship in the compiled stylesheet** (`styles.css` / `_ds_bundle.css`) — use them directly; you do not need a Tailwind config or any token import. Standard Tailwind color utilities still work, but reach for these first so designs stay on-brand.

## Surfaces

| Utility | Hex | Use for |
|---|---|---|
| `bg-bg` | `#f5f8ff` | The app background. Whole-page canvas. |
| `bg-panel` | `#ffffff` | Cards, headers, primary surfaces floating over `bg-bg`. |
| `bg-surface2` | `#eef3fc` | Cool inset/secondary panel (nested or muted regions). |
| `bg-accent` | `#3b82f6` | Solid accent fill — primary buttons, slider thumbs. Use sparingly. |
| `bg-accent-soft` | `#eff6ff` | Tinted accent background — active menu item, "Cloud" badge, selected chips. |

## Text

| Utility | Hex | Use for |
|---|---|---|
| `text-ink` | `#0f1b35` | Primary text, headings, default body. |
| `text-ink-soft` | `#3a4a6b` | Secondary text that's still high-priority. |
| `text-muted` | `#7488a8` | Supporting/helper text, captions, placeholders, eyebrow labels. |
| `text-accent` | `#3b82f6` | Links/highlights, the brand glyph, active state text. |
| `text-accent-ink` | `#1e40af` | Stronger accent text — emphasis on accent surfaces, taglines. |

## Borders & focus

| Utility | Hex | Use for |
|---|---|---|
| `border-line` | `#e2e9f5` | Default hairline on every surface and divider. |
| `border-line-strong` | `#cdd9ee` | Heavier separation where `border-line` is too faint. |
| `ring-accent` | `#3b82f6` | Focus ring. Always pair with `focus-visible:ring-2` (idiom: `focus-visible:ring-2 focus-visible:ring-accent/40`). |

## When to use which

- **Page vs card:** `bg-bg` for the page, `bg-panel` for the thing on it. Nest with `bg-surface2` when you need a third quiet layer.
- **Text hierarchy:** `text-ink` (primary) → `text-ink-soft` (secondary) → `text-muted` (tertiary/help). Don't skip straight from ink to muted for body copy that still matters.
- **Accent discipline:** `bg-accent` is for the single primary action; `bg-accent-soft` + `text-accent` is the everyday "selected/active/info" pairing. `text-accent-ink` is the darker accent for emphasis.
- **Status colors** are plain Tailwind, used narrowly: errors `text-red-600` (destructive hover `hover:bg-red-50`); neutral chips `bg-zinc-100 text-muted`.

## Idiomatic snippets

```tsx
// Active / selected row in a menu
<div className="bg-accent-soft text-accent">Selected model</div>

// Cloud vs Local badge
<span className="rounded bg-accent-soft px-1 py-0.5 text-[10px] font-medium text-accent">Cloud</span>
<span className="rounded bg-zinc-100 px-1 py-0.5 text-[10px] font-medium text-muted">Local</span>

// Focusable control
<button className="rounded-xl border border-line focus-visible:ring-2 focus-visible:ring-accent/40">…</button>
```

## Do / Don't

- DO let `text-accent` / `bg-accent` be rare and meaningful — they signal "this is the action / this is selected."
- DON'T hardcode hex values; use the named utilities so the palette stays consistent and themeable.
- DON'T use `bg-accent` for large background areas or use multiple accents on one surface.
