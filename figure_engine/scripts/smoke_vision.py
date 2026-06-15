#!/usr/bin/env python
"""Phase A 리스크 게이트: GPT 비전 critic 경로 검증(GPT-only 전환 후).

Gemini VLM critic을 GPT 비전으로 교체했으므로, 설정된 ``vision_model``이 이미지를 받아
``CritiqueResult`` 구조적 출력을 정상 반환하는지 1회 호출로 확인한다. 작은 PNG라 저비용.

    python scripts/smoke_vision.py
"""

from __future__ import annotations

import asyncio
import io

from dotenv import load_dotenv

from figgen.config import get_settings
from figgen.pipeline.critic import CritiqueResult
from figgen.providers.base import ImageInput, user

load_dotenv()


def _sample_png() -> bytes:
    """라벨 두 개가 겹쳐 그려진 작은 figure 모사 PNG — critic이 'overlap'을 잡는지 본다."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 400), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([60, 120, 280, 260], outline=(40, 80, 160), width=4)
    d.rectangle([360, 120, 580, 260], outline=(40, 80, 160), width=4)
    d.line([280, 190, 360, 190], fill=(0, 0, 0), width=3)
    d.text((90, 180), "Encoder", fill=(0, 0, 0))
    d.text((100, 188), "Encoder", fill=(200, 0, 0))  # 의도적 겹침
    d.text((400, 180), "Decoder", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def main() -> int:
    s = get_settings()
    if not s.has_key("openai"):
        print("[openai] OPENAI_API_KEY 없음 — 건너뜀")
        return 0
    from figgen.providers.openai_client import OpenAIClient

    client = OpenAIClient(s.openai_api_key.get_secret_value(), s.vision_model)
    print(f"=== GPT 비전 critic ({client.name}) ===")
    try:
        out = await client.complete_structured(
            [user("의도: encoder→decoder 다이어그램. 라벨 겹침/위치를 비평하라.",
                  images=[ImageInput(mime="image/png", data=_sample_png())])],
            CritiqueResult,
            system=("You are a figure design critic. Return a CritiqueResult: issues "
                    "(severity/category/element_ids/description/suggestion), overall_score 0-10, "
                    "verdict (accept if score>=8 and no critical/major issues, else revise)."),
        )
        print(f"  ✓ verdict={out.verdict} score={out.overall_score} issues={len(out.issues)}")
        for i in out.issues[:5]:
            print(f"    - [{i.severity}/{i.category}] {i.description[:80]}")
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {type(e).__name__}: {str(e)[:240]}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
