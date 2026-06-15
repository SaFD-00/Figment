"""Pydantic JSON Schema → OpenAI structured-output 스키마 변환.

이 모듈이 최대 기술 리스크(재귀 ``Node`` discriminated-union의 구조적 출력)를 흡수한다.

- **OpenAI strict**(`response_format=json_schema, strict=True`): 재귀 ``$ref``를 지원하므로
  보존하되, 전 객체 ``additionalProperties:false`` + 전 property ``required`` 화 + strict
  미지원 키워드(pattern/min·maxLength/format/min·maximum/min·maxItems 등) 제거가 필요하다.

실패 시 최후 방어선은 JSON-mode + Pydantic 검증 + repair 재시도다
(``build_json_mode_prompt`` 가 그 프롬프트 텍스트를 만든다).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

# strict 모드 미지원 → description으로 이전 후 제거할 검증 키워드
_DROP_KEYWORDS = (
    "pattern",
    "minLength",
    "maxLength",
    "format",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minItems",
    "maxItems",
    "uniqueItems",
    "default",
    "title",
    "discriminator",
    "examples",
)


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI strict
# ─────────────────────────────────────────────────────────────────────────────
def to_openai_strict(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic 모델 → OpenAI strict json_schema (재귀 ``$ref`` 보존)."""
    schema = model.model_json_schema(ref_template="#/$defs/{model}")
    defs = schema.pop("$defs", {})
    root = _strict_node(schema)
    if defs:
        root["$defs"] = {name: _strict_node(d) for name, d in defs.items()}
    return root


def _move_constraints_to_description(node: dict[str, Any]) -> None:
    """제거 대상 검증 키워드를 description 텍스트로 이전한다."""
    notes: list[str] = []
    for kw in _DROP_KEYWORDS:
        if kw in node and kw not in ("default", "title", "discriminator", "examples"):
            notes.append(f"{kw}={node[kw]}")
    if notes:
        existing = node.get("description", "")
        suffix = "constraints: " + ", ".join(notes)
        node["description"] = f"{existing} ({suffix})".strip() if existing else suffix


def _strict_node(node: Any) -> Any:
    if not isinstance(node, dict):
        return node

    # $ref는 형제 키를 버리고 단독 참조로 (OpenAI strict는 재귀 $ref 지원)
    if "$ref" in node:
        return {"$ref": node["$ref"]}

    out = dict(node)
    _move_constraints_to_description(out)
    for kw in _DROP_KEYWORDS:
        out.pop(kw, None)

    # const → enum 단일값 (strict는 enum 사용)
    if "const" in out:
        out["enum"] = [out.pop("const")]

    # anyOf / oneOf → anyOf
    for key in ("anyOf", "oneOf"):
        if key in out:
            subs = [_strict_node(s) for s in out.pop(key)]
            out["anyOf"] = subs

    # 객체: 전 property required + additionalProperties false
    if out.get("type") == "object" or "properties" in out:
        props = out.get("properties")
        if isinstance(props, dict):
            out["properties"] = {k: _strict_node(v) for k, v in props.items()}
            out["required"] = list(props.keys())
        else:
            out.setdefault("properties", {})
            out["required"] = []
        out["additionalProperties"] = False
        out.setdefault("type", "object")

    # 배열
    if out.get("type") == "array" and "items" in out:
        out["items"] = _strict_node(out["items"])

    return out


# ─────────────────────────────────────────────────────────────────────────────
# 공통 폴백
# ─────────────────────────────────────────────────────────────────────────────
def supports_native_schema(provider: str, model: type[BaseModel]) -> bool:
    """provider가 해당 모델의 네이티브 스키마를 표현 가능한지. GPT-only라 openai만 True."""
    return provider == "openai"  # OpenAI strict는 재귀 $ref 지원


def build_json_mode_prompt(model: type[BaseModel]) -> str:
    """JSON-mode 폴백용 — 스키마 요약을 시스템 프롬프트에 삽입할 텍스트."""
    schema = model.model_json_schema()
    schema_str = json.dumps(schema, ensure_ascii=False, indent=2)
    return (
        "다음 JSON Schema를 정확히 따르는 단일 JSON 객체만 출력하라. "
        "마크다운 코드펜스·주석·설명 없이 순수 JSON만 반환한다. "
        "discriminated union은 각 객체의 'type' 필드로 구분된다.\n\n"
        f"```json\n{schema_str}\n```"
    )
