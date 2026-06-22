"""엔드투엔드 생성 흐름 — 웹앱 JobManager가 호출하는 단일 진입점.

Stage: PLANNING → STYLING → ASSETS → RENDERING → CRITIC → FINALIZING.
Phase 3에서는 CRITIC이 no-op 통과(Phase 4에서 활성). 각 Stage 진입/완료 시 progress_cb로
StageEvent를 발행한다(웹 SSE).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path

from ..assets.generator import AssetGenerator, AssetRequest
from ..assets.store import AssetStore
from ..config import Settings
from ..jobs.models import JobRecord, Stage, StageEvent
from ..jobs.store import FileStore
from ..layout.engine import LayoutEngine
from ..providers.registry import get_image_client, get_llm
from ..render.exporter import export_figure
from ..render.resolver import resolve
from ..schema.figure_spec import CONTAINER_TYPES, FigureSpec
from ..schema.patch import PatchOp, SpecPatch, apply_patch
from ..schema.requests import GenerationRequest
from ..styles.presets import get_preset
from .planner import Planner, RefStyleReport
from .stylist import Stylist

ProgressCb = Callable[[StageEvent], None]


async def research_context(description: str, provider: str, settings: Settings) -> str:
    """웹검색 그라운딩(베스트-에포트) 공용 헬퍼 — one-shot 잡과 대화형 /plan이 공유.

    mock/빈 설명/실패 시 빈 문자열. 호출 측이 research on/off를 판단한다.
    """
    if not description or provider == "mock":
        return ""
    try:
        return await get_llm("research", settings, provider_override=provider).web_research(
            description, max_chars=settings.research_max_chars)
    except Exception:  # noqa: BLE001
        return ""


class Orchestrator:
    def __init__(self, settings: Settings, store: FileStore, *, critic_enabled: bool = False):
        self.settings = settings
        self.store = store
        self.critic_enabled = critic_enabled

    async def run(self, job: JobRecord, progress_cb: ProgressCb) -> dict[str, str]:
        seq = {"n": 0}

        def emit(etype, stage=None, status=None, message="", progress=None, payload=None):
            seq["n"] += 1
            progress_cb(StageEvent(
                seq=seq["n"], job_id=job.job_id, type=etype, stage=stage, status=status,
                message=message, progress=progress, payload=payload or {}, ts=time.time()))

        req = self._core_request(job)
        provider = job.request.model_prefs.provider
        job_dir = self.store.job_dir(job.project_id, job.job_id)
        asset_store = AssetStore(job_dir / "assets")

        # ── PLANNING (task별 분기) ──────────────────────────────────────────────
        emit("stage", Stage.PLANNING, "started", "구조 계획 중…")
        task = job.request.task
        planner = Planner(
            get_llm("planner", self.settings, provider_override=provider),
            get_llm("classifier", self.settings, provider_override=provider))
        style_ref: RefStyleReport | None = None  # STYLING까지 운반(참조 스타일 실반영)
        if task == "vectorize":
            spec = await self._vectorize_spec(job, asset_store, emit)
        elif task == "refine":
            spec = await self._refine_spec(job, asset_store, provider, emit)
        elif task == "sketch":
            research_ctx = await self._research(req, provider, emit)
            # 스케치 잡에 2번째 이미지가 있으면 그것을 스타일 참조로 분석(1번째=스케치).
            style_ref = await self._describe_style_ref_2nd(job, planner, emit)
            from .sketch import sketch_to_spec

            emit("stage", Stage.PLANNING, "progress", "스케치 정제 중…")
            spec = await sketch_to_spec(
                planner, req, asset_store, self.settings, provider,
                research_ctx=research_ctx, style_ref=style_ref)
        elif job.request.parent_job_id:
            spec = await self._edit_spec(job, req, asset_store, provider, emit)
        else:
            ftype = await planner.classify(req)
            emit("log", Stage.PLANNING, "progress", f"figure_type = {ftype}")
            research_ctx = await self._research(req, provider, emit)
            style_ref = await self._describe_reference(req, planner, emit)
            from .routing import is_image_first

            if is_image_first(ftype):
                from .scene import generate_scene_spec

                emit("stage", Stage.PLANNING, "progress", "장면 일러스트 생성 중…")
                spec = await generate_scene_spec(
                    planner, req, asset_store, self.settings, provider,
                    research_ctx=research_ctx, figure_type=ftype, style_ref=style_ref,
                    aspect=req.aspect)
            else:
                spec = await planner.plan(
                    req, ftype, research_ctx=research_ctx, style_ref=style_ref)
        emit("stage", Stage.PLANNING, "completed", f"요소 {len(spec.element_ids())}개")

        # ── STYLING ──────────────────────────────────────────────────────────
        emit("stage", Stage.STYLING, "started", f"프리셋 {req.style_preset} 적용")
        spec = self._apply_style(spec, req, style_ref)
        emit("stage", Stage.STYLING, "completed")

        # ── ASSETS ───────────────────────────────────────────────────────────
        emit("stage", Stage.ASSETS, "started", "에셋 생성 중…")
        spec = await self._generate_assets(spec, req, asset_store, provider, emit)
        spec = await self._generate_charts(spec, req, asset_store, provider, emit)
        if self.settings.diagram_box_icons and spec.figure_type == "method_diagram":
            from .diagram_icons import generate_box_icons

            emit("stage", Stage.ASSETS, "progress", "박스 일러스트 생성 중…")
            spec = await generate_box_icons(spec, req, asset_store, self.settings, provider)
        emit("stage", Stage.ASSETS, "completed")

        # ── RENDERING (초기) ───────────────────────────────────────────────────
        emit("stage", Stage.RENDERING, "started", "렌더링 중…")
        bundle = self._render_bundle(spec, asset_store, job.job_id, emit)
        emit("stage", Stage.RENDERING, "completed")

        # ── CRITIC ───────────────────────────────────────────────────────────
        # 신규 생성(generate)·스케치만 비평 — edit/refine/vectorize는 결정론적이라 제외.
        emit("stage", Stage.CRITIC, "started", "비평 단계")
        if (self.critic_enabled and req.max_critic_iters > 0
                and task in ("generate", "sketch") and not job.request.parent_job_id):
            from .critic import Critic

            vlm = get_llm("critic", self.settings, provider_override=provider)
            critic = Critic(vlm, max_iters=req.max_critic_iters)

            def _on_round(rnd, _png):
                emit("preview", Stage.CRITIC, "progress", f"비평 라운드 {rnd + 1}",
                     payload={"critic_round": rnd + 1})

            try:
                improved, history = await critic.run(
                    spec, intent=req.description, asset_store=asset_store, on_round=_on_round)
                scores = ", ".join(str(c.overall_score) for c in history)
                emit("log", Stage.CRITIC, "progress", f"점수: {scores}")
                if improved.model_dump() != spec.model_dump():
                    spec = improved
                    bundle = self._render_bundle(spec, asset_store, job.job_id, emit)
                    emit("log", Stage.CRITIC, "progress", "패치 반영 후 재렌더")
            except Exception as e:  # noqa: BLE001
                emit("log", Stage.CRITIC, "progress", f"critic 건너뜀: {e}")
        else:
            emit("log", Stage.CRITIC, "progress", "critic 비활성 (통과)")
        emit("stage", Stage.CRITIC, "completed")

        # ── FINALIZING ───────────────────────────────────────────────────────
        emit("stage", Stage.FINALIZING, "started", "산출물 저장 중…")
        artifacts = self._write_artifacts(job_dir, spec, bundle)
        emit("preview", Stage.FINALIZING, "completed", "완료",
             payload={"preview_url": f"/api/jobs/{job.job_id}/files/preview.png"})
        return artifacts

    # ── 내부 ───────────────────────────────────────────────────────────────────
    def _apply_style(self, spec: FigureSpec, req: GenerationRequest,
                     style_ref: RefStyleReport | None) -> FigureSpec:
        """STYLING 적용. 우선순위: 수동 팔레트 > 참조 스타일 > 프리셋."""
        styler = Stylist()
        if req.palette:
            ss = get_preset(req.style_preset).model_copy(update={"palette": req.palette[:6]})
            return styler.apply(spec, req.style_preset, custom=ss)
        if style_ref and style_ref.palette_hex:
            return styler.from_report(spec, style_ref, base_preset=req.style_preset)
        return styler.apply(spec, req.style_preset)

    async def _research(self, req: GenerationRequest, provider: str, emit) -> str:
        """웹검색 그라운딩(베스트-에포트). job당 1회, 실패해도 빈 문자열로 진행."""
        if not req.research or provider == "mock":
            return ""
        emit("stage", Stage.PLANNING, "progress", "웹 리서치 그라운딩 중…")
        ctx = await research_context(req.description, provider, self.settings)
        if not ctx:
            emit("log", Stage.PLANNING, "progress", "리서치 건너뜀")
            return ""
        emit("log", Stage.PLANNING, "progress", f"리서치 컨텍스트 {len(ctx)}자")
        return ctx

    async def _describe_style_ref_2nd(
        self, job: JobRecord, planner: Planner, emit
    ) -> RefStyleReport | None:
        """sketch 잡: 2번째 첨부 이미지를 스타일 참조로 분석(1번째는 스케치라 제외)."""
        ids = job.request.reference_image_ids
        if len(ids) < 2:
            return None
        p = self.store.resolve_input(ids[1])
        if not p or not p.exists():
            return None
        emit("stage", Stage.PLANNING, "progress", "스케치 스타일 참조 분석 중…")
        try:
            report = await planner.describe_reference(p.read_bytes())
        except Exception as e:  # noqa: BLE001
            emit("log", Stage.PLANNING, "progress", f"스타일 참조 건너뜀: {e}")
            return None
        emit("log", Stage.PLANNING, "progress", f"스케치 스타일 참조({len(report.palette_hex)}색)")
        return report

    async def _describe_reference(
        self, req: GenerationRequest, planner: Planner, emit
    ) -> RefStyleReport | None:
        """스타일 참조 이미지 분석(베스트-에포트). generate 경로에 참조 이미지가 첨부되면
        팔레트/밀도/레이아웃을 뽑아 생성 프롬프트에 스타일 가이드로 반영. 실패해도 job은 진행.

        대화가 스타일 참조를 generate 태스크로 라우팅하므로, 이 경로에 reference_image_path가
        있다는 것 자체가 'reference_role=style'을 의미한다(JobRequest엔 role 필드 없음).
        """
        if not req.reference_image_path:
            return None
        try:
            data = Path(req.reference_image_path).read_bytes()
        except OSError as e:
            emit("log", Stage.PLANNING, "progress", f"스타일 참조 로드 실패: {e}")
            return None
        emit("stage", Stage.PLANNING, "progress", "스타일 참조 분석 중…")
        try:
            report = await planner.describe_reference(data)
        except Exception as e:  # noqa: BLE001
            emit("log", Stage.PLANNING, "progress", f"스타일 참조 건너뜀: {e}")
            return None
        emit("log", Stage.PLANNING, "progress",
             f"스타일 참조 반영(팔레트 {len(report.palette_hex)}색, {report.density})")
        return report

    def _core_request(self, job: JobRecord) -> GenerationRequest:
        r = job.request
        data_refs: dict[str, str] = {}
        for fid in r.data_file_ids:
            p = self.store.resolve_input(fid)
            if p:
                data_refs[fid] = str(p)
        ref_path = None
        if r.reference_image_ids:
            p = self.store.resolve_input(r.reference_image_ids[0])
            ref_path = str(p) if p else None
        return GenerationRequest(
            description=r.prompt, paper_text=r.paper_text, figure_type=r.figure_type,
            style_preset=r.style_preset, palette=r.palette, aspect=r.aspect,
            provider=r.model_prefs.provider,
            max_critic_iters=r.model_prefs.max_critic_rounds, research=r.research,
            data_refs=data_refs, reference_image_path=ref_path)

    async def _edit_spec(self, job: JobRecord, req: GenerationRequest, asset_store: AssetStore,
                         provider: str, emit) -> FigureSpec:
        """부분 재생성/인-캔버스 편집 — 부모 spec+에셋 로드 후 canvas_op 또는 PartialEditor 적용."""
        parent = self.store.load_job(job.request.parent_job_id)
        parent_dir = self.store.job_dir(job.project_id, job.request.parent_job_id) if parent else None
        spec_path = (parent_dir / "spec.json") if parent_dir else None
        if not (spec_path and spec_path.exists()):
            # 부모 없음 → 신규 생성 폴백
            planner = Planner(get_llm("planner", self.settings, provider_override=provider))
            ft = await planner.classify(req)
            return await planner.plan(req, ft)

        # 부모 에셋을 자식 job 에셋 스토어로 복사(임베드 렌더 시 해석 가능하게)
        self._seed_assets(parent_dir, asset_store)
        spec = FigureSpec.model_validate_json(spec_path.read_text("utf-8"))

        op = job.request.canvas_op
        if op is not None:
            spec = await self._apply_canvas_op(spec, op, asset_store, provider, emit)
        elif job.request.edit is not None:
            try:
                from .partial_edit import PartialEditor

                editor = PartialEditor(get_llm("editor", self.settings, provider_override=provider))
                spec = await editor.edit(spec, job.request.edit)
                emit("log", Stage.PLANNING, "progress",
                     f"부분 재생성: {len(job.request.edit.target_element_ids) or '전체'} 요소")
            except Exception as e:  # noqa: BLE001
                emit("log", Stage.PLANNING, "progress", f"부분편집 폴백: {e}")
        return spec.model_copy(update={"stylesheet": None})

    async def _apply_canvas_op(self, spec: FigureSpec, op, asset_store: AssetStore,
                               provider: str, emit) -> FigureSpec:
        """인-캔버스 도구(region_redraw/text_edit/white_bg/upscale)를 적용해 새 spec 반환."""
        if op.kind == "text_edit":
            # LLM 없이 결정론적 라벨/텍스트 교체
            node = spec.find(op.target_element_id)
            path = "text" if getattr(node, "type", None) == "text" else "label"
            patch = SpecPatch(ops=[PatchOp(op="set", target_id=op.target_element_id, path=path,
                                           value=op.text or "")])
            new_spec, errs = apply_patch(spec, patch)
            emit("log", Stage.PLANNING, "progress",
                 f"텍스트 편집: {op.target_element_id}" + (f" (오류 {len(errs)})" if errs else ""))
            return new_spec

        # 래스터 연산 — 선택 요소의 asset_id를 편집해 새 asset으로 교체
        from . import image_ops

        node = spec.find(op.target_element_id)
        asset_id = getattr(node, "asset_id", None) if node is not None else None
        if not asset_id:
            emit("log", Stage.PLANNING, "progress",
                 f"이미지 편집 대상 아님: {op.target_element_id} (건너뜀)")
            return spec
        client = get_image_client(self.settings, provider_override=provider)
        if op.kind == "region_redraw":
            new_id = await image_ops.region_redraw(client, asset_store, asset_id, op.instruction,
                                                   op.region)
        elif op.kind == "white_bg":
            new_id = await image_ops.white_background(client, asset_store, asset_id)
        else:  # upscale
            new_id = await image_ops.refine_asset(client, asset_store, asset_id, ["upscale"])
        emit("log", Stage.PLANNING, "progress", f"{op.kind}: {op.target_element_id} → {new_id}")

        ops = [PatchOp(op="set", target_id=op.target_element_id, path="asset_id", value=new_id)]
        # 벡터화 변형이 있었으면 새 래스터로 재벡터화(없으면 svg 제거)
        new_svg = self._maybe_vectorize(asset_store, new_id)
        if getattr(node, "svg_asset_id", None) is not None:
            ops.append(PatchOp(op="set", target_id=op.target_element_id, path="svg_asset_id",
                               value=new_svg))
        new_spec, _ = apply_patch(spec, SpecPatch(ops=ops))
        return new_spec

    # ── 신규 surface (sketch는 pipeline/sketch.py 위임, refine/vectorize는 아래) ──────
    def _load_input_image(self, job: JobRecord, emit) -> bytes | None:
        ids = job.request.reference_image_ids or job.request.data_file_ids
        if not ids:
            emit("log", Stage.PLANNING, "progress", "입력 이미지 없음")
            return None
        p = self.store.resolve_input(ids[0])
        return p.read_bytes() if p and p.exists() else None

    def _maybe_vectorize(self, asset_store: AssetStore, png_asset_id: str) -> str | None:
        if not getattr(self.settings, "scene_vectorize", True):
            return None
        png = asset_store.get_png(png_asset_id)
        if png is None:
            return None
        try:
            from ..fullimage.vectorize import vectorize_png

            return asset_store.put(vectorize_png(png), "image/svg+xml", kind="illustration_svg")
        except Exception:  # noqa: BLE001
            return None

    async def _refine_spec(self, job: JobRecord, asset_store: AssetStore, provider: str,
                           emit) -> FigureSpec:
        """Figure Refiner — 업로드 래스터를 업스케일/색보정/노이즈제거 후 풀블리드 spec."""
        from ..fullimage.composer import build_overlay_spec, canvas_mm_for_image
        from . import image_ops

        data = self._load_input_image(job, emit)
        if data is None:
            raise ValueError("refine: 입력 이미지가 필요합니다")
        base_id = asset_store.put(data, "image/png", kind="illustration")
        client = get_image_client(self.settings, provider_override=provider)
        modes = job.request.refine_modes or ["upscale"]
        emit("stage", Stage.PLANNING, "progress", f"보정 중… ({', '.join(modes)})")
        refined_id = await image_ops.refine_asset(client, asset_store, base_id, modes)
        refined = asset_store.get_png(refined_id) or data
        svg_id = self._maybe_vectorize(asset_store, refined_id)
        return build_overlay_spec(refined_id, [], canvas_mm=canvas_mm_for_image(refined),
                                  figure_type="scientific_illustration", base_svg_asset_id=svg_id)

    async def _vectorize_spec(self, job: JobRecord, asset_store: AssetStore, emit) -> FigureSpec:
        """Image Vectorization — 업로드 PNG/JPG → vtracer SVG 풀블리드 spec."""
        from ..fullimage.composer import build_overlay_spec, canvas_mm_for_image
        from ..fullimage.vectorize import vectorize_png

        data = self._load_input_image(job, emit)
        if data is None:
            raise ValueError("vectorize: 입력 이미지가 필요합니다")
        base_id = asset_store.put(data, "image/png", kind="illustration")
        emit("stage", Stage.PLANNING, "progress", "벡터화 중…")
        svg_id = asset_store.put(vectorize_png(data), "image/svg+xml", kind="illustration_svg")
        return build_overlay_spec(base_id, [], canvas_mm=canvas_mm_for_image(data),
                                  figure_type="scientific_illustration", base_svg_asset_id=svg_id)

    def _seed_assets(self, parent_dir: Path, asset_store: AssetStore) -> None:
        """부모 job의 에셋(manifest + 파일)을 자식 에셋 스토어로 복사 후 인덱스 재로딩."""
        import shutil

        src = parent_dir / "assets"
        if not src.exists():
            return
        for f in src.glob("*"):
            if f.is_file():
                shutil.copy2(f, asset_store.root / f.name)
        asset_store._load()

    async def _generate_assets(self, spec, req, asset_store, provider, emit) -> FigureSpec:
        targets = [
            n for n, _ in spec.iter_elements()
            if getattr(n, "type", None) == "image" and getattr(n, "gen_prompt", None)
            and not getattr(n, "asset_id", None)
        ]
        if not targets:
            return spec
        gen = AssetGenerator(self.settings, asset_store, provider_override=provider)
        total = len(targets)

        async def _one(i, node):
            emit("stage", Stage.ASSETS, "progress", f"아이콘 {i + 1}/{total}",
                 payload={"done": i, "total": total})
            r = await gen.generate(AssetRequest(
                description=node.gen_prompt or node.alt, kind="icon",
                style_preset=req.style_preset, transparency_required=node.needs_transparency))
            return node.id, r.asset_id, r.cached

        results = await asyncio.gather(*[_one(i, n) for i, n in enumerate(targets)])
        mapping = {eid: aid for eid, aid, _ in results}
        if any(c for _, _, c in results):
            emit("log", Stage.ASSETS, "progress", "캐시 히트 포함")
        data = spec.model_dump()
        _apply_asset_ids(data["root"], mapping)
        return FigureSpec.model_validate(data)

    async def _generate_charts(self, spec, req, asset_store, provider, emit) -> FigureSpec:
        charts = [
            n for n, _ in spec.iter_elements()
            if getattr(n, "type", None) == "chart" and not getattr(n, "svg_asset_id", None)
        ]
        if not charts:
            return spec
        from ..charts.track import ChartTrack

        track = ChartTrack(get_llm("chart_coder", self.settings, provider_override=provider),
                           asset_store)
        ss = spec.stylesheet
        updates: dict[str, tuple[str | None, str | None]] = {}
        for i, ch in enumerate(charts):
            emit("stage", Stage.ASSETS, "progress", f"차트 {i + 1}/{len(charts)}")
            data_path = None
            if ch.data_ref and ch.data_ref in req.data_refs:
                from pathlib import Path as _P

                data_path = _P(req.data_refs[ch.data_ref])
            try:
                built = await track.build(ch, data_path, ss)
                updates[ch.id] = (built.svg_asset_id, built.code_asset_id)
            except Exception as e:  # noqa: BLE001
                emit("log", Stage.ASSETS, "progress", f"차트 {ch.id} 실패: {e}")
        if not updates:
            return spec
        data = spec.model_dump()
        _apply_chart_ids(data["root"], updates)
        return FigureSpec.model_validate(data)

    def _render_bundle(self, spec, asset_store, job_id, emit):
        layout = LayoutEngine().layout(spec)
        fig = resolve(spec, layout, spec.stylesheet)
        for w in layout.warnings:
            emit("log", Stage.RENDERING, "progress",
                 f"⚠ {w.kind}: {','.join(w.element_ids)} {w.detail}")
        return export_figure(fig, asset_store, asset_href_base=f"/api/jobs/{job_id}/assets/")

    def _write_artifacts(self, job_dir: Path, spec: FigureSpec, bundle) -> dict[str, str]:
        _w(job_dir / "spec.json",
           json.dumps(spec.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2)
           .encode())
        _w(job_dir / "figure.svg", bundle.svg.encode())
        _w(job_dir / "preview.svg", bundle.preview_svg.encode())
        _w(job_dir / "figure.pptx", bundle.pptx)
        _w(job_dir / "preview.png", bundle.preview_png)
        return {
            "spec.json": "spec.json", "figure.svg": "figure.svg", "preview.svg": "preview.svg",
            "figure.pptx": "figure.pptx", "preview.png": "preview.png",
        }


def _apply_asset_ids(node: dict, mapping: dict[str, str]) -> None:
    if node.get("type") == "image" and node.get("id") in mapping:
        node["asset_id"] = mapping[node["id"]]
    if node.get("type") in CONTAINER_TYPES:
        for c in node.get("children", []):
            _apply_asset_ids(c, mapping)
    elif node.get("type") == "free":
        for it in node.get("items", []):
            _apply_asset_ids(it["node"], mapping)


def _apply_chart_ids(node: dict, updates: dict[str, tuple]) -> None:
    if node.get("type") == "chart" and node.get("id") in updates:
        svg_id, code_id = updates[node["id"]]
        node["svg_asset_id"] = svg_id
        node["code_asset_id"] = code_id
    if node.get("type") in CONTAINER_TYPES:
        for c in node.get("children", []):
            _apply_chart_ids(c, updates)
    elif node.get("type") == "free":
        for it in node.get("items", []):
            _apply_chart_ids(it["node"], updates)


def _w(path: Path, data: bytes) -> None:
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
