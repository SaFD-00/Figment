# Figment — Brand & Voice

Figment is a **light-blue, Inter-based SaaS** for generating and editing **scientific figures and images**. Users turn ideas, sketches, or references into editable figures, then refine and export them (PPTX / SVG / PNG). Your designs should feel **calm, precise, and technical-but-approachable** — a serious research tool that never feels intimidating.

## Personality

- **Calm & uncluttered.** Lots of light-blue-tinted whitespace (`bg-bg`), one clear primary action per surface, no visual noise.
- **Precise.** Clean type, tight tracking on headings (`tracking-tight`), exact spacing. This is a tool for people who care about detail.
- **Technical but approachable.** Plain, confident language. Explain capability, not jargon. A single subtle accent glyph (`✦`) is the brand mark; emoji are used sparingly as functional icons (🖼️ for an empty image slot), never decoratively.

## Voice (UI copy)

- Lead with the benefit, verb-first: "Turn ideas into editable scientific figures," "Generate from text, sketches, or references."
- Short, scannable, sentence case. Headlines can split across lines with the payoff in `text-accent`, e.g. "Figures & images, **made effortless.**"
- Helper/empty/tip text is quiet and useful: `text-muted`, `text-xs`/`text-sm`. Example empty state: "No projects yet. Generate your first image above." Example tip: "Tip: press ⌘/Ctrl + Enter to start."
- Errors are direct, never alarmist: "Enter a prompt or attach an image first." Render error text as `text-sm text-red-600`.

## Typography

- **Inter** for everything (`font-sans`); it ships with the design system. Body sets at `text-base text-ink`.
- Headings: bold to extrabold, navy ink, tight tracking. Hero `text-4xl font-extrabold tracking-tight sm:text-5xl`; section/card heading `text-lg font-bold text-ink`; eyebrow label `text-sm font-semibold uppercase tracking-wide text-muted`.
- Body/supporting text `text-sm text-muted`; fine print `text-xs text-muted`.

## Do / Don't

- DO keep one primary `Button variant="primary"` per surface; pair it with `secondary`/`ghost` for lesser actions.
- DO use the accent color as a deliberate highlight (one word in a headline, an active state), not as a fill for large areas.
- DON'T introduce a second brand color, gradients, or dark surfaces — Figment is `color-scheme: light` only.
- DON'T write playful or hyped copy. Stay factual and quietly confident.
