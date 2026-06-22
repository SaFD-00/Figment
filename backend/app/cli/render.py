"""Terminal output helpers for the CLI — color, a single-line progress bar, and tables.

Everything routes to stdout EXCEPT the progress bar, which writes to stderr so a command's
real result (an asset path, an enhanced prompt) stays clean on stdout and is pipeable.
Color auto-disables when stdout/stderr is not a TTY.
"""
from __future__ import annotations

import sys
from typing import Iterable

_COLOR = sys.stdout.isatty()

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"


def _wrap(text: str, code: str) -> str:
    return f"{code}{text}{_RESET}" if _COLOR else text


def bold(t: str) -> str: return _wrap(t, _BOLD)
def dim(t: str) -> str: return _wrap(t, _DIM)
def green(t: str) -> str: return _wrap(t, _GREEN)
def yellow(t: str) -> str: return _wrap(t, _YELLOW)
def red(t: str) -> str: return _wrap(t, _RED)
def cyan(t: str) -> str: return _wrap(t, _CYAN)


def status_label(status: str) -> str:
    """Colorize PASS/SKIP/FAIL for the verify matrix."""
    return {"PASS": green, "SKIP": yellow, "FAIL": red}.get(status, str)(f"{status:<4}")


class ProgressBar:
    """A \\r-updated single-line bar on stderr. No-op when disabled or not a TTY."""

    def __init__(self, *, enabled: bool = True, label: str = "", width: int = 24) -> None:
        self.enabled = enabled and sys.stderr.isatty()
        self.label = label
        self.width = width
        self._active = False

    def update(self, frac: float, msg: str = "") -> None:
        if not self.enabled:
            return
        frac = max(0.0, min(1.0, frac))
        filled = int(self.width * frac)
        bar = "#" * filled + "-" * (self.width - filled)
        msg = (msg or "")[:40]
        sys.stderr.write(f"\r{self.label} [{bar}] {int(frac * 100):3d}% {msg:<40}")
        sys.stderr.flush()
        self._active = True

    def done(self) -> None:
        if self.enabled and self._active:
            sys.stderr.write("\n")
            sys.stderr.flush()
        self._active = False

    # alias so callers can use it as a guard in finally:
    close = done


def table(headers: list[str], rows: Iterable[list[str]]) -> str:
    """Render a fixed-width text table (header bolded)."""
    rows = [[str(c) for c in r] for r in rows]
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(_strip(c)))
    def fmt(cells: list[str], is_header: bool) -> str:
        out = []
        for i, c in enumerate(cells):
            pad = widths[i] - len(_strip(c))
            out.append((bold(c) if is_header else c) + " " * max(0, pad))
        return "  ".join(out).rstrip()
    lines = [fmt(headers, True)]
    lines.append(dim("─" * (sum(widths) + 2 * (len(headers) - 1))))
    lines.extend(fmt(r, False) for r in rows)
    return "\n".join(lines)


def _strip(s: str) -> str:
    """Length of visible text, ignoring ANSI codes (for column alignment)."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", s)
