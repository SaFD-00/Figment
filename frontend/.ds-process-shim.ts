// Minimal browser polyfill for Node's `process`. Next.js internals bundled via
// next/link + next/navigation read process.env.__NEXT_* and process.nextTick at
// module init; the converter's esbuild only defines process.env.NODE_ENV, so a
// bare `process` is otherwise undefined in the preview/runtime and the IIFE
// crashes on load. Imported FIRST in the entry so it runs before any next
// module initializes. Guarded so a real bundler-provided process is never
// clobbered (this is infrastructure, not mock data — safe in shipped designs).
const g = globalThis as unknown as {
  process?: { env: Record<string, string | undefined>; nextTick?: (cb: (...a: unknown[]) => void, ...a: unknown[]) => void };
};
const nextTick = (cb: (...a: unknown[]) => void, ...args: unknown[]) => setTimeout(() => cb(...args), 0);
if (typeof g.process === "undefined") {
  g.process = { env: { NODE_ENV: "development" }, nextTick };
} else if (typeof g.process.nextTick !== "function") {
  g.process.nextTick = nextTick;
}
export {};
