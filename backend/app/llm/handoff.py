"""Streaming GENSPEC extractor. Detection is purely structural: a well-formed
<GENSPEC>...</GENSPEC> block means "ready to generate"; its absence means "still chatting".

Usage:
    extractor = GenSpecExtractor()
    async for tok in llm.chat_stream(...):
        visible = extractor.feed(tok)   # tokens to show the user (block is withheld)
        if visible: yield visible
    spec, raw, err = extractor.finish()  # spec is a validated GenSpec or None
"""
from __future__ import annotations

import json
from typing import Optional

from pydantic import ValidationError

from app.schemas.genspec import GenSpec

OPEN = "<GENSPEC>"
CLOSE = "</GENSPEC>"


class GenSpecExtractor:
    def __init__(self) -> None:
        self._buf = ""           # full accumulated text
        self._emitted = 0        # chars already returned as visible
        self._in_block = False

    def feed(self, token: str) -> str:
        """Append a token; return the slice of NEW text safe to show (outside any GENSPEC block)."""
        self._buf += token
        # Find the block start once.
        start = self._buf.find(OPEN)
        if start == -1:
            # No block yet. Hold back a small tail in case OPEN is split across tokens.
            safe_end = max(self._emitted, len(self._buf) - len(OPEN))
            out = self._buf[self._emitted:safe_end]
            self._emitted = safe_end
            return out
        # Block has started: emit anything before it that we haven't yet, then withhold the rest.
        if self._emitted < start:
            out = self._buf[self._emitted:start]
            self._emitted = start
            return out
        return ""

    def finish(self) -> tuple[Optional[GenSpec], Optional[str], Optional[str]]:
        """Flush remaining visible text is the caller's job via feed(); here we parse the block.
        Returns (genspec, raw_json, error)."""
        start = self._buf.find(OPEN)
        if start == -1:
            return None, None, None  # pure chat turn
        end = self._buf.find(CLOSE, start)
        if end == -1:
            return None, None, "GENSPEC block was not closed"
        raw = self._buf[start + len(OPEN):end].strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return None, raw, f"invalid JSON: {e}"
        try:
            return GenSpec.model_validate(data), raw, None
        except ValidationError as e:
            return None, raw, f"schema error: {e}"

    def trailing_visible(self) -> str:
        """Any visible text after a (closed) block, or remaining pre-block text. Usually empty."""
        start = self._buf.find(OPEN)
        if start == -1:
            out = self._buf[self._emitted:]
            self._emitted = len(self._buf)
            return out
        end = self._buf.find(CLOSE, start)
        if end == -1:
            return ""
        after = end + len(CLOSE)
        out = self._buf[after:]
        return out.strip()
