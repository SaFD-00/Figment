#!/usr/bin/env python
"""Phase D 라이브 스모크: gpt-image edit(마스크 인페인트) 라운드트립 확인.

Region Redraw/White BG/Upscale/Figure Refiner의 백본인 ``images.edit`` 경로가 동작하는지
샘플 이미지 + 마스크로 1회 호출한다. 키가 있을 때만 동작.

    python scripts/smoke_edits.py
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

from dotenv import load_dotenv

from figgen.config import get_settings
from figgen.pipeline.image_ops import build_region_mask

load_dotenv()
OUT = Path("/tmp/figgen_smoke")
OUT.mkdir(exist_ok=True)


def _sample() -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1024, 1024), (245, 247, 250))
    d = ImageDraw.Draw(img)
    d.ellipse([200, 200, 824, 824], fill=(80, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def main() -> int:
    s = get_settings()
    if not s.has_key("openai"):
        print("[openai] OPENAI_API_KEY 없음 — 건너뜀")
        return 0
    from figgen.providers.openai_client import OpenAIImageClient

    client = OpenAIImageClient(s.openai_api_key.get_secret_value(), s.image_model)
    print(f"=== gpt-image edit ({client.name}) ===")
    src = _sample()
    mask = build_region_mask((1024, 1024), [0.55, 0.1, 0.35, 0.35])  # 우상단 영역만 재생성
    try:
        res = await client.edit(src, "add a small green leaf in the masked region",
                                mask=mask, background="opaque", input_fidelity="high")
        (OUT / "edit_result.png").write_bytes(res.data)
        print(f"  ✓ {len(res.data)} bytes → {OUT}/edit_result.png")
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {type(e).__name__}: {str(e)[:240]}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
