#!/usr/bin/env python
"""라이브 클라이언트 경로 스모크 — figgen의 실제 OpenAIClient를 그대로 호출(GPT-only).

smoke_structured.py와 달리 파이프라인이 쓰는 코드 경로(temperature·이미지 입력·repair)를
그대로 탄다. gpt-5.x 추론 모델의 temperature 호환성 같은 실전 이슈를 잡는 게 목적.
작은 스키마라 저비용.

    python scripts/smoke_clients.py
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from figgen.config import get_settings
from figgen.providers.base import Message

load_dotenv()


class Leaf(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["leaf"] = "leaf"
    label: str


class Box(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["box"] = "box"
    children: list[Node]


Node = Annotated[Leaf | Box, Field(discriminator="type")]


class MiniSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: Node
    title: str | None = None


Box.model_rebuild()
MiniSpec.model_rebuild()

PROMPT = ("Make a box containing two leaves labeled 'encoder' and 'decoder', "
          "title 'Transformer'. Follow the schema exactly.")
MSG = [Message(role="user", content=PROMPT)]


async def _test(name: str, client) -> None:
    print(f"\n=== {name} ({client.name}) ===")
    # 1) 자유 텍스트
    try:
        txt = await client.complete([Message(role="user", content="Reply with the single word OK.")])
        print(f"  complete()           ✓  → {txt[:60]!r}")
    except Exception as e:  # noqa: BLE001
        print(f"  complete()           ✗  {type(e).__name__}: {str(e)[:240]}")
    # 2) 구조적 출력
    try:
        out = await client.complete_structured(MSG, MiniSpec)
        print(f"  complete_structured()✓  → {out.model_dump_json()[:120]}")
    except Exception as e:  # noqa: BLE001
        print(f"  complete_structured()✗  {type(e).__name__}: {str(e)[:240]}")


async def main() -> int:
    s = get_settings()
    if s.has_key("openai"):
        from figgen.providers.openai_client import OpenAIClient

        await _test("OpenAI", OpenAIClient(s.openai_api_key.get_secret_value(), s.planner_model))
    else:
        print("[openai] 키 없음 — 건너뜀")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
