#!/usr/bin/env python
"""Phase B 라이브 스모크: OpenAI Responses web_search 그라운딩 경로 확인.

설정된 ``research_model``이 web_search 도구로 과학적 맥락 텍스트를 반환하는지 1회 호출로
검증한다. 비용/지연이 있으므로 키가 있을 때만 동작.

    python scripts/smoke_research.py ["주제"]
"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv

from figgen.config import get_settings

load_dotenv()


async def main() -> int:
    s = get_settings()
    if not s.has_key("openai"):
        print("[openai] OPENAI_API_KEY 없음 — 건너뜀")
        return 0
    from figgen.providers.openai_client import OpenAIClient

    query = sys.argv[1] if len(sys.argv) > 1 else "the citric acid cycle (Krebs cycle)"
    client = OpenAIClient(s.openai_api_key.get_secret_value(), s.research_model)
    print(f"=== web_research ({client.name}) ===\n주제: {query}\n")
    ctx = await client.web_research(query, max_chars=s.research_max_chars)
    if ctx:
        print(f"✓ {len(ctx)}자 수집\n{'-' * 60}\n{ctx[:1200]}")
    else:
        print("✗ 빈 컨텍스트 — web_search 미가용/실패(베스트-에포트라 파이프라인은 계속 진행)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
