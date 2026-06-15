"use client";

// A small inline spinner for button loading states ONLY.
// For job progress, use the determinate ProgressOverlay instead.
export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`}
      aria-hidden
    />
  );
}
