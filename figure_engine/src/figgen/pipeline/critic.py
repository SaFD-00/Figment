"""VLM 자기비평 루프 — 진단과 수정을 분리한 2콜 구조 + best-snapshot.

VLM에 (a) 렌더 PNG (b) 요소 id 오버레이 debug PNG (c) 결정론적 LayoutWarning을 함께 제공한다.
제한된 SpecPatch만 허용해 회귀를 차단하고, 매 라운드 (spec, score)를 보존해 최고 점수를 채택.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..layout.engine import LayoutEngine
from ..providers.base import ImageInput, LLMClient, user
from ..render.preview import downsample_png, svg_to_png
from ..render.resolver import resolve
from ..render.svg_renderer import SvgRenderer
from ..schema.figure_spec import FigureSpec
from ..schema.patch import SpecPatch, apply_patch


class CritiqueIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: Literal["critical", "major", "minor"] = "minor"
    category: Literal["overlap", "clipping", "imbalance", "semantic", "style", "text", "flow"] = "style"
    element_ids: list[str] = Field(default_factory=list)
    description: str = ""
    suggestion: str = ""


class CritiqueResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issues: list[CritiqueIssue] = Field(default_factory=list)
    overall_score: int = Field(ge=0, le=10, default=8)
    verdict: Literal["accept", "revise"] = "accept"


_DIAGNOSE = (
    "You are a figure design critic. Given a rendered figure (image 1) and an id-overlay debug "
    "image (image 2) plus deterministic layout warnings, return a CritiqueResult: list issues "
    "(severity/category/element_ids/description/suggestion), an overall_score 0-10, and verdict "
    "(accept if score>=8 and no critical/major issues, else revise)."
)
_PATCH = (
    "Given the critique issues and the current FigureSpec, return a MINIMAL SpecPatch that fixes "
    "ONLY those issues (ops: set/remove/insert_child/move_child/replace_element; each with reason)."
)
# scientific_illustration: 장면 아트는 래스터 1장이고 모든 텍스트는 Free 위 편집가능 라벨이다.
# 따라서 비평은 '각 라벨이 올바른 영역에 놓였는가'에 집중하고, 수정은 좌표/문구로 제한한다.
_DIAGNOSE_SCENE = (
    "You are a scientific-figure critic. Image 1 is a rendered illustration: one drawn scene "
    "with editable text labels overlaid; image 2 is an id-overlay debug view. Check that each "
    "label sits ON its correct region of the scene, that labels do not overlap each other or "
    "fall off-canvas, and that the title reads well. Do NOT critique the artwork's internal "
    "detail (it is a fixed raster). Return a CritiqueResult (issues with element_ids referencing "
    "the label ids, overall_score 0-10, verdict accept if score>=8 and no critical/major issues)."
)
_PATCH_SCENE = (
    "Given the critique issues and the current FigureSpec (a Free root: one base image + text "
    "labels), return a MINIMAL SpecPatch that repositions or rewrites ONLY the mislabeled items. "
    "Use ONLY `set` ops on a FreeItem's x_frac/y_frac (0..1) or a label's text. Never touch the "
    "base_image, never add/remove elements."
)


class Critic:
    def __init__(self, vlm: LLMClient, *, max_iters: int = 2, accept_score: int = 8):
        self.vlm = vlm
        self.max_iters = max_iters
        self.accept_score = accept_score
        self.engine = LayoutEngine()

    async def run(
        self,
        spec: FigureSpec,
        intent: str,
        *,
        asset_store=None,
        on_round: Callable[[int, bytes], None] | None = None,
    ) -> tuple[FigureSpec, list[CritiqueResult]]:
        snapshots: list[tuple[FigureSpec, int]] = []
        history: list[CritiqueResult] = []
        cur = spec
        prev_score = -1
        no_improve = 0
        is_scene = spec.figure_type == "scientific_illustration"
        diagnose_sys = _DIAGNOSE_SCENE if is_scene else _DIAGNOSE
        patch_sys = _PATCH_SCENE if is_scene else _PATCH

        for rnd in range(self.max_iters):
            png, debug_png, warn_text = self._render(cur, asset_store)
            if on_round:
                on_round(rnd, png)
            critique = await self.vlm.complete_structured(
                [user(f"의도: {intent}\n결정론적 경고:\n{warn_text}",
                      images=[ImageInput(mime="image/png", data=downsample_png(png)),
                              ImageInput(mime="image/png", data=downsample_png(debug_png))])],
                CritiqueResult, system=diagnose_sys)
            history.append(critique)
            snapshots.append((cur, critique.overall_score))

            major = sum(1 for i in critique.issues if i.severity in ("critical", "major"))
            if critique.verdict == "accept" or major == 0 or rnd == self.max_iters - 1:
                break
            if critique.overall_score <= prev_score:
                no_improve += 1
                if no_improve >= 2:
                    break
            prev_score = critique.overall_score

            patch = await self.vlm.complete_structured(
                [user("Issues: " + critique.model_dump_json()
                      + "\nSpec: " + cur.model_dump_json())],
                SpecPatch, system=patch_sys)
            cur, _ = apply_patch(cur, patch)

        best_spec = max(snapshots, key=lambda s: s[1])[0] if snapshots else spec
        return best_spec, history

    def _render(self, spec: FigureSpec, asset_store) -> tuple[bytes, bytes, str]:
        layout = self.engine.layout(spec)
        fig = resolve(spec, layout, spec.stylesheet)
        renderer = SvgRenderer(asset_store, embed_images=True)
        png = svg_to_png(renderer.render(fig))
        debug_png = svg_to_png(renderer.render(fig, debug=True))
        warns = "\n".join(
            f"- [{w.severity}] {w.kind}: {','.join(w.element_ids)} {w.detail}" for w in layout.warnings
        ) or "(없음)"
        return png, debug_png, warns
