#!/usr/bin/env python
"""M0 라이브 스모크: 재귀 discriminated-union FigureSpec의 구조적 출력 성공률 측정.

키 확보 후 실행한다. schema_transform 만 의존(독립 실행). 모델 ID는 `.env`(FIGGEN_*) 오버라이드.

    python scripts/smoke_structured.py [--n 10]

성공 기준: provider별 파싱 성공률 ≥ 9/10. 실패 시 repair 1회로 복구되는지도 기록.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Annotated, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from figgen.providers import schema_transform as st

load_dotenv()

PROMPT = (
    "Produce a nested layout spec: a 'box' whose children contain another 'box' "
    "with two 'leaf' nodes (labels 'encoder' and 'decoder'), plus a top-level title. "
    "Use the provided schema exactly."
)


class Leaf(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["leaf"] = "leaf"
    label: str
    size: float | None = None


class Box(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["box"] = "box"
    children: list[Node]
    gap: float = 4.0


Node = Annotated[Leaf | Box, Field(discriminator="type")]


class MiniSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: Node
    title: str | None = None


MiniSpec.model_rebuild()
Box.model_rebuild()


def _try_openai(n: int, model: str) -> None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("[openai] OPENAI_API_KEY 없음 — 건너뜀")
        return
    from openai import OpenAI

    client = OpenAI(api_key=key)
    schema = st.to_openai_strict(MiniSpec)
    ok = 0
    for i in range(n):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": PROMPT}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "MiniSpec", "schema": schema, "strict": True},
                },
            )
            MiniSpec.model_validate_json(resp.choices[0].message.content)
            ok += 1
        except (ValidationError, Exception) as e:  # noqa: BLE001
            print(f"  [openai {i}] 실패: {type(e).__name__}: {str(e)[:120]}")
    print(f"[openai:{model}] 성공 {ok}/{n}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    args = ap.parse_args()
    print("OpenAI strict 스키마 미리보기:")
    print(json.dumps(st.to_openai_strict(MiniSpec), ensure_ascii=False)[:400], "...\n")
    _try_openai(args.n, os.environ.get("FIGGEN_PLANNER_MODEL", "gpt-5.4"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
