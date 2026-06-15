#!/usr/bin/env python
"""M0 라이브 스모크: 이미지 생성 모델 유효성 + 투명 PNG alpha 채널 확인.

    python scripts/smoke_image.py

gpt-image-1.5(투명 네이티브) → alpha 채널 assert. GPT-only.
모델 ID는 `.env`(FIGGEN_*) 오버라이드.
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

load_dotenv()
OUT = Path("/tmp/figgen_smoke")
OUT.mkdir(exist_ok=True)


def _openai() -> None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("[openai] 키 없음 — 건너뜀")
        return
    from openai import OpenAI

    model = os.environ.get("FIGGEN_DEFAULT_IMAGER", "gpt-image-1.5")
    client = OpenAI(api_key=key)
    try:
        resp = client.images.generate(
            model=model,
            prompt="a single flat minimal vector icon of a neural network node, centered",
            size="1024x1024",
            background="transparent",
            output_format="png",
        )
        data = base64.b64decode(resp.data[0].b64_json)
        img = Image.open(io.BytesIO(data))
        has_alpha = img.mode in ("RGBA", "LA") or "transparency" in img.info
        (OUT / "openai_transparent.png").write_bytes(data)
        print(f"[openai:{model}] OK, mode={img.mode}, alpha={has_alpha} → {OUT}/openai_transparent.png")
        assert has_alpha, "투명 배경 PNG에 alpha 채널이 없음"
    except Exception as e:  # noqa: BLE001
        print(f"[openai:{model}] 실패: {type(e).__name__}: {str(e)[:160]}")


if __name__ == "__main__":
    _openai()
