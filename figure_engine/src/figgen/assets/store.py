"""job 귀속 버전 체인 AssetStore — 이미지·차트 산출물을 함께 흡수.

차트 산출물도 kind='chart_svg'|'chart_png'|'chart_code'로 통합(별도 ChartStore 폐지, C6).
부분 재생성 시 parent_id로 버전 체인을 이어 undo를 지원한다.
렌더러는 get_png/get_svg/get_chart_png로 asset_id를 바이트로 해석한다.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

AssetKind = Literal[
    "icon", "illustration", "illustration_svg", "photo", "chart_svg", "chart_png", "chart_code"
]
_EXT = {"chart_svg": "svg", "illustration_svg": "svg", "chart_code": "py"}


class Asset(BaseModel):
    asset_id: str
    kind: AssetKind
    mime: str
    filename: str
    parent_id: str | None = None
    meta: dict = Field(default_factory=dict)


class AssetStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._manifest = self.root / "manifest.json"
        self._index: dict[str, Asset] = {}
        self._load()

    def _load(self) -> None:
        if self._manifest.exists():
            try:
                data = json.loads(self._manifest.read_text("utf-8"))
                self._index = {k: Asset.model_validate(v) for k, v in data.items()}
            except Exception:  # noqa: BLE001
                self._index = {}

    def _save(self) -> None:
        data = {k: v.model_dump() for k, v in self._index.items()}
        _atomic_write(self._manifest, json.dumps(data, ensure_ascii=False).encode())

    def put(
        self, data: bytes | str, mime: str, *, kind: AssetKind, parent_id: str | None = None
    ) -> str:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        asset_id = "ast_" + hashlib.sha1(raw).hexdigest()[:14]
        ext = _EXT.get(kind, "png")
        filename = f"{asset_id}.{ext}"
        _atomic_write(self.root / filename, raw)
        self._index[asset_id] = Asset(
            asset_id=asset_id, kind=kind, mime=mime, filename=filename, parent_id=parent_id)
        self._save()
        return asset_id

    def get(self, asset_id: str) -> Asset | None:
        return self._index.get(asset_id)

    def exists(self, asset_id: str) -> bool:
        return asset_id in self._index

    def _bytes(self, asset_id: str) -> bytes | None:
        a = self._index.get(asset_id)
        if a is None:
            return None
        p = self.root / a.filename
        return p.read_bytes() if p.exists() else None

    def get_png(self, asset_id: str) -> bytes | None:
        return self._bytes(asset_id)

    def get_svg(self, asset_id: str) -> str | None:
        b = self._bytes(asset_id)
        return b.decode("utf-8") if b is not None else None

    def get_chart_png(self, asset_id: str) -> bytes | None:
        # asset_id는 chart_svg id — 연결된(parent=svg) chart_png를 찾는다
        for a in self._index.values():
            if a.parent_id == asset_id and a.kind == "chart_png":
                return self._bytes(a.asset_id)
        return self._bytes(asset_id)

    def put_chart(self, svg: str, png: bytes, code: str) -> tuple[str, str]:
        """차트 산출물(svg+png+code)을 연결 저장. (svg_asset_id, code_asset_id) 반환."""
        svg_id = self.put(svg, "image/svg+xml", kind="chart_svg")
        self.put(png, "image/png", kind="chart_png", parent_id=svg_id)
        code_id = self.put(code, "text/x-python", kind="chart_code", parent_id=svg_id)
        return svg_id, code_id

    def versions(self, asset_id: str) -> list[Asset]:
        """asset_id의 조상 체인(루트→현재)."""
        chain: list[Asset] = []
        cur = self._index.get(asset_id)
        while cur is not None:
            chain.append(cur)
            cur = self._index.get(cur.parent_id) if cur.parent_id else None
        return list(reversed(chain))


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
