"""mock provider — 키 없이 파이프라인 전체를 오프라인 구동.

타입별 캔드 FigureSpec(구조 유효) + PIL placeholder 에셋을 결정론적으로 생성한다.
실 provider(openai)는 동일 Protocol을 구현하며, 라이브 검증은 별도 스크립트로 분리.
"""

from __future__ import annotations

import io
import re
from typing import Any

from pydantic import BaseModel

from ..schema.figure_spec import FigureSpec
from .base import AssetResult, ImageInput, Message

_TYPE_RE = re.compile(r"\[\[figure_type:(\w+)\]\]")


def _slug(text: str, fallback: str, idx: int) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    s = re.sub(r"_+", "_", s)[:30]
    if not s or not s[0].isalpha():
        s = f"{fallback}_{idx}"
    return s


def _detect_type(system: str, messages: list[Message]) -> str:
    # plan()은 system에 [[figure_type:X]] 태그를 넣는다 — 있으면 그게 정답.
    m = _TYPE_RE.search(system + " ".join(msg.content for msg in messages))
    if m:
        return m.group(1)
    # classify()는 태그가 없다 — system(=classify.md, 'chart/plot' 등 키워드 포함)이 아니라
    # 사용자 메시지(설명)에만 키워드 매칭해야 오분류하지 않는다.
    low = " ".join(msg.content for msg in messages).lower()
    # graphical_abstract를 chart('graph' 부분매칭)보다 먼저 — 'graphical'이 'graph'에 걸리지 않게.
    if "graphical abstract" in low:
        return "graphical_abstract"
    if "chart" in low or "plot" in low or "graph" in low:
        return "chart"
    arch_kw = ("architecture", "pipeline", "diagram", "block", "encoder", "decoder",
               "module", "framework", "system")
    if any(k in low for k in arch_kw):
        return "method_diagram"
    if "concept" in low:
        return "concept"
    # 공격적 기본값: 아키텍처/차트/명시적 GA가 아니면 풍부한 장면 일러스트
    return "scientific_illustration"


def _stages(description: str) -> list[str]:
    parts = re.split(r"\s*(?:->|→|=>|,|;|\bthen\b|\bto\b)\s*", description)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 2:
        return [p[:28] for p in parts[:5]]
    words = description.split()
    if len(words) >= 3:
        third = max(1, len(words) // 3)
        return [
            " ".join(words[:third])[:28],
            " ".join(words[third : 2 * third])[:28],
            " ".join(words[2 * third :])[:28],
        ]
    return ["Input", description[:28] or "Process", "Output"]


class MockLLMClient:
    name = "mock"

    async def complete(self, messages: list[Message], *, system: str = "",
                       temperature: float = 0.3) -> str:
        return "mock response"

    async def web_research(self, query: str, *, max_chars: int = 4000) -> str:
        return ""  # 오프라인 — 네트워크 호출 없음

    async def complete_structured(
        self,
        messages: list[Message],
        schema: type[BaseModel],
        *,
        system: str = "",
        images: list[ImageInput] | None = None,
        max_repair: int = 2,
    ) -> Any:
        name = schema.__name__
        ftype = _detect_type(system, messages)
        desc = messages[-1].content if messages else "Example"

        if name == "FigureSpec":
            return _mock_figure(ftype, desc)
        if name == "SceneBrief":
            return _mock_scene_brief(schema, desc)
        if name == "PlanTurn":
            return _mock_plan_turn(schema, messages)
        if name == "ClassifyResult":
            return schema(figure_type=ftype, confidence=0.92, reason="mock 분류")
        if name == "ContentPlan":
            return _mock_content_plan(schema, desc)
        if name == "CritiqueResult":
            return schema(issues=[], overall_score=9, verdict="accept")
        if name == "SpecPatch":
            return schema(ops=[], reason="mock no-op")
        if name == "RefStyleReport":
            return schema(palette_hex=["#3C5488", "#E64B35"], density="medium",
                          layout_pattern="left-to-right", font_feel="sans-serif")
        if name == "ChartCode":
            return schema(code="ax.bar(['A','B','C'],[1,2,3])", expects_data_file=False)
        if name == "EnhancePromptResponse":
            base = desc.split("(figure_type hint:")[0].strip()
            return schema(prompt=f"A publication-quality scientific figure of {base[:200]}")
        try:
            return schema()  # 전 필드 기본값 보유 시
        except Exception as e:  # noqa: BLE001
            from .base import StructuredOutputError

            raise StructuredOutputError(f"mock가 {name} 생성 불가") from e


def _mock_content_plan(schema: type[BaseModel], desc: str) -> Any:
    stages = _stages(desc)
    entities = [{"name": s, "kind": "module", "description": ""} for s in stages]
    relations = [
        {"source": stages[i], "target": stages[i + 1], "kind": "flow", "label": None}
        for i in range(len(stages) - 1)
    ]
    return schema(entities=entities, relations=relations, narrative=desc[:200])


def _mock_plan_turn(schema: type[BaseModel], messages: list[Message]) -> Any:
    """오프라인 대화 — 첫 턴에 즉시 ready=true. 첨부 마커로 task를 결정론 라우팅."""
    text = messages[-1].content if messages else ""
    body = text.split("[첨부 정보]")[0]  # 사용자 발화만 — 첨부 안내문 키워드 제외
    low = body.lower()
    has_image = "이미지" in text and "[첨부 정보]" in text
    task, role, refine_modes = "generate", "none", []
    if has_image:
        if "벡터" in low or "vectorize" in low or "svg" in low:
            task, role = "vectorize", "refine"
        elif any(k in low for k in ("정제", "refine", "업스케일", "upscale", "노이즈", "색보정")):
            task, role, refine_modes = "refine", "refine", ["upscale"]
        elif "스케치" in low or "sketch" in low:
            task, role = "sketch", "sketch"
        else:
            task, role = "generate", "style"
    ftype = _detect_type("", messages)
    user_lines = [ln[5:].strip() for ln in body.splitlines() if ln.startswith("User:")]
    desc = (user_lines[-1] if user_lines else body.strip())[:400] or "scientific figure"
    summary = f"· 종류: {ftype}\n· 설명: {desc[:80]}"
    reply = f"계획을 정리했어요 — '{ftype}' figure로 생성합니다. 아래 ‘생성’을 누르면 진행돼요."
    plan = {
        "task": task, "figure_type": ftype, "title": desc[:40], "description": desc,
        "summary": summary, "style_preset": None, "refine_modes": refine_modes,
        "reference_role": role,
    }
    return schema(reply=reply, ready=True, plan=plan)


def _mock_scene_brief(schema: type[BaseModel], desc: str) -> Any:
    stages = _stages(desc)
    n = len(stages)
    labels = [
        {"text": s[:24], "nx": (i + 1) / (n + 1), "ny": 0.5,
         "anchor": "center", "font_role": "heading"}
        for i, s in enumerate(stages)
    ]
    return schema(
        scene_prompt=f"a cohesive scientific illustration of {desc[:80]}",
        title=desc[:40], aspect="wide", labels=labels,
    )


def _mock_figure(ftype: str, desc: str) -> FigureSpec:
    if ftype == "chart":
        spec = {
            "figure_type": "chart",
            "title": desc[:40],
            "root": {"type": "column", "id": "root", "gap_mm": 5, "padding_mm": 6, "children": [
                {"type": "chart", "id": "chart_main", "chart_kind": "grouped_bar", "brief": desc[:80]},
                {"type": "text", "id": "caption", "text": desc[:120], "text_role": "caption",
                 "h_align": "center"},
            ]},
        }
    elif ftype == "concept":
        spec = {
            "figure_type": "concept",
            "title": desc[:40],
            "root": {"type": "column", "id": "root", "gap_mm": 6, "padding_mm": 6, "children": [
                {"type": "text", "id": "title", "text": desc[:50], "text_role": "title",
                 "h_align": "center"},
                {"type": "row", "id": "body", "gap_mm": 10, "children": [
                    {"type": "image", "id": "illus", "alt": desc[:40],
                     "gen_prompt": f"flat vector illustration of {desc[:60]}"},
                    {"type": "box", "id": "concept_box", "label": desc[:28] or "Concept",
                     "role": "model", "shape": "rounded"},
                ]},
            ]},
        }
    elif ftype == "scientific_illustration":
        # 정상 흐름은 plan_scene을 거치지만, plan()으로 직접 호출돼도 유효한
        # Free-루트 장면 spec(베이스 이미지 + 편집 라벨)을 내도록 방어.
        stages = _stages(desc)
        items = [{
            "node": {"type": "image", "id": "base_image", "alt": desc[:40] or "scene",
                     "gen_prompt": f"cohesive scientific illustration of {desc[:60]}",
                     "needs_transparency": False},
            "x_frac": 0.5, "y_frac": 0.5, "w_frac": 1.0, "h_frac": 1.0, "anchor": "center",
        }]
        for i, s in enumerate(stages):
            items.append({
                "node": {"type": "text", "id": f"lbl_{i}", "text": s[:24],
                         "text_role": "heading", "h_align": "center"},
                "x_frac": (i + 1) / (len(stages) + 1), "y_frac": 0.5, "anchor": "center",
            })
        spec = {
            "figure_type": "scientific_illustration",
            "canvas": {"width_mm": 170, "height_mm": 113},
            "root": {"type": "free", "id": "root", "items": items},
        }
    elif ftype == "graphical_abstract":
        spec = {
            "figure_type": "graphical_abstract",
            "canvas": {"width_mm": 170, "height_mm": 90},
            "root": {"type": "free", "id": "root", "items": [
                {"node": {"type": "box", "id": "ga_problem", "label": "Problem", "role": "input"},
                 "x_frac": 0.18, "y_frac": 0.4},
                {"node": {"type": "box", "id": "ga_method", "label": desc[:24] or "Method",
                          "role": "model"}, "x_frac": 0.5, "y_frac": 0.5},
                {"node": {"type": "box", "id": "ga_result", "label": "Result", "role": "output",
                          "shape": "ellipse"}, "x_frac": 0.82, "y_frac": 0.4},
            ]},
            "connectors": [
                {"id": "ga_e1", "source": "ga_problem", "target": "ga_method"},
                {"id": "ga_e2", "source": "ga_method", "target": "ga_result"},
            ],
        }
    else:  # method_diagram
        stages = _stages(desc)
        children = []
        ids = []
        for i, label in enumerate(stages):
            eid = _slug(label, "stage", i)
            while eid in ids:
                eid = f"{eid}_{i}"
            ids.append(eid)
            role = "input" if i == 0 else ("output" if i == len(stages) - 1 else "process")
            shape = "ellipse" if role in ("input", "output") else "rounded"
            children.append({"type": "box", "id": eid, "label": label, "role": role, "shape": shape})
        connectors = [
            {"id": f"flow_{i}", "source": ids[i], "target": ids[i + 1]}
            for i in range(len(ids) - 1)
        ]
        spec = {
            "figure_type": "method_diagram",
            "title": desc[:40],
            "root": {"type": "row", "id": "root", "gap_mm": 12, "padding_mm": 8,
                     "align": "center", "children": children},
            "connectors": connectors,
        }
    return FigureSpec.model_validate(spec)


class MockImageClient:
    name = "mock"

    async def generate(
        self,
        prompt: str,
        *,
        width_px: int = 1024,
        height_px: int = 1024,
        transparent: bool = True,
        style_hint: str | None = None,
    ) -> AssetResult:
        from PIL import Image, ImageDraw

        seed = sum(ord(c) for c in prompt) if prompt else 0
        palette = [(76, 114, 176), (221, 132, 82), (85, 168, 104), (196, 78, 82), (129, 114, 178)]
        color = palette[seed % len(palette)]
        bg = (0, 0, 0, 0) if transparent else (245, 247, 250, 255)
        img = Image.new("RGBA", (width_px, height_px), bg)
        d = ImageDraw.Draw(img)
        pad = int(min(width_px, height_px) * 0.16)
        d.ellipse([pad, pad, width_px - pad, height_px - pad], fill=(*color, 235),
                  outline=(255, 255, 255, 255), width=max(2, width_px // 100))
        label = (prompt or "asset").strip()[:16]
        d.text((width_px // 2, int(height_px * 0.82)), label, anchor="mm", fill=(60, 60, 60, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return AssetResult(data=buf.getvalue(), mime="image/png", has_alpha=transparent,
                           provider="mock", revised_prompt=prompt)

    async def edit(
        self,
        image: bytes,
        prompt: str,
        *,
        mask: bytes | None = None,
        size: str | None = None,
        background: str = "auto",
        input_fidelity: str = "high",
        transparent: bool = False,
    ) -> AssetResult:
        """오프라인 mock edit — 입력 위에 가시적 틴트+워터마크를 얹어 '편집됨'을 표시."""
        from PIL import Image, ImageDraw

        img = Image.open(io.BytesIO(image)).convert("RGBA")
        img = Image.alpha_composite(img, Image.new("RGBA", img.size, (124, 58, 237, 28)))
        d = ImageDraw.Draw(img)
        d.text((10, 10), f"mock-edit:{(prompt or '')[:14]}", fill=(20, 20, 20, 255))
        if not transparent:
            img = Image.alpha_composite(Image.new("RGBA", img.size, (255, 255, 255, 255)), img)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return AssetResult(data=buf.getvalue(), mime="image/png", has_alpha=transparent,
                           provider="mock", revised_prompt=prompt)
