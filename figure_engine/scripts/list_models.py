#!/usr/bin/env python
"""라이브 모델 디스커버리 — .env에 설정된 모델명이 실존하는지 확정한다.

생성 호출이 아니라 models.list 메타 조회라 비용이 거의 없다. 설정값(FIGGEN_*)과
실제 가용 목록을 대조해 ✓/✗ 를 출력한다.

    python scripts/list_models.py
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

CONFIGURED = {
    "FIGGEN_PLANNER_MODEL": os.environ.get("FIGGEN_PLANNER_MODEL", "gpt-5.4"),
    "FIGGEN_CLASSIFIER_MODEL": os.environ.get("FIGGEN_CLASSIFIER_MODEL", "gpt-5.4"),
    "FIGGEN_VISION_MODEL": os.environ.get("FIGGEN_VISION_MODEL", "gpt-5.4"),
    "FIGGEN_CHART_CODER_MODEL": os.environ.get("FIGGEN_CHART_CODER_MODEL", "gpt-5.4"),
    "FIGGEN_RESEARCH_MODEL": os.environ.get("FIGGEN_RESEARCH_MODEL", "gpt-5.4"),
    "FIGGEN_DEFAULT_IMAGER": os.environ.get("FIGGEN_DEFAULT_IMAGER", "gpt-image-1.5"),
}


def list_openai() -> set[str]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("[openai] 키 없음")
        return set()
    from openai import OpenAI

    client = OpenAI(api_key=key)
    try:
        ids = sorted(m.id for m in client.models.list().data)
    except Exception as e:  # noqa: BLE001
        print(f"[openai] models.list 실패: {type(e).__name__}: {str(e)[:200]}")
        return set()
    print(f"\n=== OpenAI 가용 모델 ({len(ids)}) ===")
    for mid in ids:
        if any(k in mid for k in ("gpt", "image", "o1", "o3", "o4", "chat")):
            print(" ", mid)
    return set(ids)


def main() -> int:
    all_ids = list_openai()
    print("\n=== 설정값 대조 ===")
    for env, val in CONFIGURED.items():
        # 정확 일치 또는 prefix 매칭(버전 suffix 대비)
        exact = val in all_ids
        prefix = [m for m in all_ids if m.startswith(val)] if not exact else []
        mark = "✓" if exact else ("~" if prefix else "✗")
        extra = "" if exact else (f"  → 후보: {prefix[:3]}" if prefix else "  (목록에 없음)")
        print(f"  {mark} {env} = {val}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
