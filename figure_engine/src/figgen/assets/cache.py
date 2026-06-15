"""전역 콘텐츠 주소 에셋 캐시 (~/.figgen/assets_cache, 홈·비동기화).

키 = sha256(model + 정규화 프롬프트 + size + transparent + preset_version). Critic 반복 루프에서
동일 아이콘 재요청 시 API 비용/지연을 크게 절감한다. preset_version으로 프롬프트 개선 시 자동 무효화.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from ..config import get_settings


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


class AssetCache:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else get_settings().resolved_asset_cache_dir()
        self.root.mkdir(parents=True, exist_ok=True)

    def key(
        self, model: str, prompt: str, size: str, transparent: bool, preset_version: str = "v1"
    ) -> str:
        raw = f"{model}|{_normalize(prompt)}|{size}|{int(transparent)}|{preset_version}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def get(self, key: str) -> bytes | None:
        p = self.root / f"{key}.png"
        if p.exists():
            return p.read_bytes()
        return None

    def put(self, key: str, png: bytes, meta: dict | None = None) -> Path:
        p = self.root / f"{key}.png"
        _atomic_write_bytes(p, png)
        sidecar = self.root / f"{key}.json"
        _atomic_write_bytes(
            sidecar,
            json.dumps({**(meta or {}), "created_at": time.time()}, ensure_ascii=False).encode(),
        )
        return p

    def purge(self, older_than_days: int = 90) -> int:
        cutoff = time.time() - older_than_days * 86400
        removed = 0
        for p in self.root.glob("*.png"):
            if p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
                (p.with_suffix(".json")).unlink(missing_ok=True)
                removed += 1
        return removed


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
