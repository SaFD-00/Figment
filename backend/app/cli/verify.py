"""`figment verify` — exercise every feature pipeline (local + cloud) and print a PASS/SKIP/FAIL
matrix. Drives the SAME in-process job path as `generate`, so it tests the real production code.

Each case declares prerequisites (ComfyUI, model weights, Ollama tag, OpenRouter key, network).
An unmet prerequisite is a clean SKIP with a precise reason — never a FAIL. A met case actually
runs (a real generation / LLM call / post-op) and asserts a plausible result. Exit code = #FAIL.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Optional

from PIL import Image

from app import deps
from app.cli import render, testdata
from app.cli.runtime import app_runtime, run_genspec, stage_image_asset
from app.comfy.templates import validate_required_nodes
from app.config import get_settings
from app.db import repo
from app.engines import model_ready
from app.engines.cloud import cloud_key_present
from app.llm.prompts import build_enhance_messages
from app.llm.routing import chat_stream
from app.models_catalog.registry import (
    CONTROLNET_FILES,
    IPADAPTER_FILES,
    LLM_MODELS,
    MODELS,
    UPSCALE_MODEL,
)
from app.orchestrator import pipeline
from app.schemas.genspec import GenSpec, Mode, ReferenceImage
from app.services import export_ops

_GROUP_ORDER = ["LOCAL", "CLOUD", "LLM", "POSTOP"]


# ── prerequisites ────────────────────────────────────────────────────────────────
@dataclass
class Prereqs:
    comfy: bool = False
    ollama_ver: Optional[str] = None
    ollama_tags: list[str] = field(default_factory=list)
    openrouter: bool = False
    net_ok: bool = False
    offline: bool = False
    report: dict = field(default_factory=dict)  # validate_required_nodes output (or {})


async def _probe(offline: bool) -> Prereqs:
    pre = Prereqs(offline=offline)
    pre.comfy = await deps.comfy().ping()
    if pre.comfy:
        pre.report = await validate_required_nodes(deps.comfy())
    pre.ollama_ver = await deps.ollama().version()
    if pre.ollama_ver:
        pre.ollama_tags = await deps.ollama().installed_models()
    pre.openrouter = cloud_key_present("openrouter")
    pre.net_ok = (await testdata.fetch_sample(testdata.SEED_SOURCE, offline=offline)) is not None
    return pre


def _models_dir_has(sub: str, filename: str) -> bool:
    return (get_settings().models_dir / sub / filename).exists()


def _unmet(needs: list[str], pre: Prereqs) -> Optional[str]:
    """Return a joined skip-reason if any prerequisite is unmet, else None (case may run)."""
    reasons: list[str] = []
    for n in needs:
        if n == "comfy" and not pre.comfy:
            reasons.append("ComfyUI not reachable")
        elif n == "ollama" and not pre.ollama_ver:
            reasons.append("Ollama not reachable")
        elif n == "openrouter" and not pre.openrouter:
            reasons.append("OPENROUTER_API_KEY not set")
        elif n == "net" and not pre.net_ok:
            reasons.append("offline / sample image unavailable")
        elif n.startswith("model:"):
            mid = n.split(":", 1)[1]
            if not model_ready(MODELS[mid]):
                primary = MODELS[mid].files.get("unet") or MODELS[mid].files.get("checkpoint") or "weights"
                reasons.append(f"weight file missing: {primary}")
        elif n.startswith("model-tag:"):
            mid = n.split(":", 1)[1]
            tag = LLM_MODELS[mid].cloud_model_id
            if tag not in pre.ollama_tags:
                reasons.append(f"ollama model not pulled: {tag}")
        elif n == "upscale-model":
            if not _models_dir_has("upscale_models", UPSCALE_MODEL):
                reasons.append(f"weight file missing: {UPSCALE_MODEL}")
        elif n.startswith("cnet:"):
            ctype = n.split(":", 1)[1]
            if not _models_dir_has("controlnet", CONTROLNET_FILES[ctype]):
                reasons.append(f"weight file missing: {CONTROLNET_FILES[ctype]}")
        elif n == "ipadapter":
            if not _models_dir_has("ipadapter", IPADAPTER_FILES["ipadapter"]):
                reasons.append(f"weight file missing: {IPADAPTER_FILES['ipadapter']}")
            elif not _models_dir_has("clip_vision", IPADAPTER_FILES["clip_vision"]):
                reasons.append(f"weight file missing: {IPADAPTER_FILES['clip_vision']}")
            elif pre.report.get("missing", {}).get("reference (ip-adapter)"):
                reasons.append("IP-Adapter nodes not installed")
        elif n == "controlnet-nodes":
            miss = []
            if pre.report.get("missing", {}).get("controlnet"):
                miss.append("ControlNet nodes")
            if "CannyEdgePreprocessor" in pre.report.get("missing_optional", []):
                miss.append("Canny preprocessor")
            if miss:
                reasons.append(" + ".join(miss) + " not installed")
    return "; ".join(reasons) if reasons else None


# ── samples (staged once per run into the verify project) ─────────────────────────
@dataclass
class Samples:
    source_path: Optional[Path] = None
    source: Optional[str] = None
    ref1: Optional[str] = None
    ref2: Optional[str] = None
    mask: Optional[str] = None


async def _stage_samples(pid: str, pre: Prereqs) -> Samples:
    if not pre.net_ok:
        return Samples()
    src = await testdata.fetch_sample(testdata.SEED_SOURCE, offline=pre.offline)
    r1 = await testdata.fetch_sample(testdata.SEED_REF1, offline=pre.offline)
    r2 = await testdata.fetch_sample(testdata.SEED_REF2, offline=pre.offline)
    s = Samples(source_path=src)
    s.source = await stage_image_asset(pid, src, "source") if src else None
    s.ref1 = await stage_image_asset(pid, r1, "reference") if r1 else None
    s.ref2 = await stage_image_asset(pid, r2, "reference") if r2 else None
    if src:
        with Image.open(src) as im:
            size = im.size
        s.mask = await stage_image_asset(pid, testdata.make_mask(size), "mask")
    return s


# ── assertions ────────────────────────────────────────────────────────────────────
def _assert_image(asset: dict, *, min_side: int = 64) -> str:
    p = Path(asset["path"])
    if not p.exists() or p.stat().st_size == 0:
        raise AssertionError("output file missing/empty")
    with Image.open(p) as im:
        im.load()
        w, h = im.size
    if w < min_side or h < min_side:
        raise AssertionError(f"implausible dims {w}x{h}")
    return f"{w}x{h}, {p.stat().st_size // 1024}KB"


def _assert_cloud(asset: dict) -> str:
    detail = _assert_image(asset)
    meta = asset.get("meta") or {}
    for k in ("svg", "pptx"):
        sc = meta.get(k)
        if not sc or not Path(sc).exists():
            raise AssertionError(f"missing {k} sidecar")
    return detail + " +svg +pptx"


# ── case model ─────────────────────────────────────────────────────────────────────
@dataclass
class VerifyCase:
    group: str
    name: str
    needs: list[str]
    run: Callable[[], Awaitable[str]]
    mode: Optional[str] = None


@dataclass
class CaseResult:
    group: str
    name: str
    status: str   # PASS | SKIP | FAIL
    detail: str
    seconds: float


def _build_cases(pid: str, pre: Prereqs, s: Samples) -> list[VerifyCase]:
    def img_local(name, mode, needs, factory, assert_fn=_assert_image):
        async def run():
            asset = await run_genspec(factory(), project_id=pid, show_progress=False, label=name[:16])
            return assert_fn(asset)
        return VerifyCase("LOCAL", name, needs, run, mode)

    def img_cloud(name, mode, factory):
        needs = ["openrouter"] + (["net"] if mode != "txt2img" else [])
        async def run():
            asset = await run_genspec(factory(), project_id=pid, show_progress=False, label=name[:16])
            return _assert_cloud(asset)
        return VerifyCase("CLOUD", name, needs, run, mode)

    def llm_chat(name, needs, llm_id):
        async def run():
            chunks = [t async for t in chat_stream([{"role": "user", "content": "Reply with one short friendly sentence."}], llm_id)]
            text = "".join(chunks).strip()
            if not text:
                raise AssertionError("empty LLM response")
            return f"{len(text)} chars"
        return VerifyCase("LLM", name, needs, run)

    def llm_enhance(name, needs, llm_id):
        async def run():
            from app.routers.prompt import _clean, _prepare_image_data_url
            url = _prepare_image_data_url(base64.b64encode(s.source_path.read_bytes()).decode("ascii"))
            msgs = build_enhance_messages("a cozy scene", None, image_url=url)
            out = _clean("".join([t async for t in chat_stream(msgs, llm_id)]))
            if not out:
                raise AssertionError("empty enhance result")
            return f"{len(out)} chars (vision)"
        return VerifyCase("LLM", name, needs, run)

    async def _upscale():
        out = await pipeline.upscale_image(deps.comfy(), s.source_path.read_bytes())
        with Image.open(io.BytesIO(out)) as im:
            w, h = im.size
        with Image.open(s.source_path) as im0:
            w0, h0 = im0.size
        if w <= w0:
            raise AssertionError("upscale did not enlarge")
        return f"{w0}x{h0} -> {w}x{h}"

    async def _removebg():
        out = await pipeline.remove_bg(s.source_path.read_bytes())
        with Image.open(io.BytesIO(out)) as im:
            im.load()
            mode = im.mode
        if mode != "RGBA":
            raise AssertionError(f"expected RGBA, got {mode}")
        return f"{len(out) // 1024}KB RGBA"

    async def _whitebg():
        out = await pipeline.white_bg(s.source_path.read_bytes())
        with Image.open(io.BytesIO(out)) as im:
            im.load()
        return f"{len(out) // 1024}KB"

    async def _svg():
        svg = await asyncio.to_thread(export_ops.png_to_svg, s.source_path.read_bytes())
        if "<svg" not in svg.lower():
            raise AssertionError("no <svg> in output")
        return f"{len(svg) // 1024}KB svg"

    async def _pptx():
        pptx = await asyncio.to_thread(export_ops.png_to_pptx, s.source_path.read_bytes())
        if pptx[:2] != b"PK":
            raise AssertionError("not a zip/pptx")
        return f"{len(pptx) // 1024}KB pptx"

    return [
        # ── LOCAL image (ComfyUI) — single SDXL checkpoint (juggernaut-xl), all modes ──
        img_local("juggernaut-xl / txt2img", "txt2img", ["comfy", "model:juggernaut-xl"],
                  lambda: GenSpec(mode=Mode.txt2img, model="juggernaut-xl",
                                  prompt="a photorealistic red fox in a snowy forest, soft light",
                                  width=768, height=768)),
        img_local("juggernaut-xl / img2img", "img2img", ["comfy", "model:juggernaut-xl", "net"],
                  lambda: GenSpec(mode=Mode.img2img, model="juggernaut-xl",
                                  prompt="the same scene as an oil painting", denoise=0.6,
                                  source_asset=s.source)),
        img_local("juggernaut-xl / edit (img2img)", "edit", ["comfy", "model:juggernaut-xl", "net"],
                  lambda: GenSpec(mode=Mode.edit, model="juggernaut-xl",
                                  prompt="make it look like winter with falling snow",
                                  source_asset=s.source)),
        img_local("juggernaut-xl / edit (mask→inpaint)", "edit", ["comfy", "model:juggernaut-xl", "net"],
                  lambda: GenSpec(mode=Mode.edit, model="juggernaut-xl",
                                  prompt="replace the masked area with a blooming flower",
                                  source_asset=s.source, mask_asset=s.mask)),
        img_local("juggernaut-xl / reference (ip-adapter)", "reference",
                  ["comfy", "model:juggernaut-xl", "ipadapter", "net"],
                  lambda: GenSpec(mode=Mode.reference, model="juggernaut-xl",
                                  prompt="a portrait in the style of this reference",
                                  reference_images=[ReferenceImage(asset=a) for a in (s.ref1,) if a])),
        img_local("juggernaut-xl / controlnet", "controlnet",
                  ["comfy", "model:juggernaut-xl", "cnet:canny", "controlnet-nodes", "net"],
                  lambda: GenSpec(mode=Mode.controlnet, model="juggernaut-xl",
                                  prompt="a neon cyberpunk street, same composition",
                                  negative_prompt="blurry", controlnet_type="canny",
                                  source_asset=s.source)),
        img_local("juggernaut-xl / inpaint", "inpaint", ["comfy", "model:juggernaut-xl", "net"],
                  lambda: GenSpec(mode=Mode.inpaint, model="juggernaut-xl",
                                  prompt="a blooming flower", negative_prompt="blurry",
                                  source_asset=s.source, mask_asset=s.mask)),

        # ── CLOUD image (OpenRouter → figure pipeline) ──
        img_cloud("gpt-image-2 / txt2img", "txt2img",
                  lambda: GenSpec(mode=Mode.txt2img, model="gpt-image-2",
                                  prompt="a labeled diagram of the water cycle")),
        img_cloud("gpt-image-2 / edit", "edit",
                  lambda: GenSpec(mode=Mode.edit, model="gpt-image-2",
                                  prompt="add clean callout labels", source_asset=s.source)),
        img_cloud("gemini-pro-image / reference", "reference",
                  lambda: GenSpec(mode=Mode.reference, model="gemini-pro-image",
                                  prompt="a figure matching this reference style",
                                  reference_images=[ReferenceImage(asset=a) for a in (s.ref1,) if a])),

        # ── LLM (chat + vision enhance) ──
        llm_chat("qwen3-vl-local / chat", ["ollama", "model-tag:qwen3-vl-local"], "qwen3-vl-local"),
        llm_enhance("qwen3-vl-local / enhance", ["ollama", "model-tag:qwen3-vl-local", "net"], "qwen3-vl-local"),
        llm_chat("gemini-2.5-flash / chat", ["openrouter"], "gemini-2.5-flash"),
        llm_enhance("gemini-2.5-flash / enhance", ["openrouter", "net"], "gemini-2.5-flash"),

        # ── POSTOP (mostly always-runnable) ──
        VerifyCase("POSTOP", "upscale (Real-ESRGAN)", ["comfy", "net", "upscale-model"], _upscale),
        VerifyCase("POSTOP", "removebg (rembg)", ["net"], _removebg),
        VerifyCase("POSTOP", "whitebg (rembg)", ["net"], _whitebg),
        VerifyCase("POSTOP", "export svg (vtracer)", ["net"], _svg),
        VerifyCase("POSTOP", "export pptx", ["net"], _pptx),
    ]


def _filter(cases: list[VerifyCase], args) -> list[VerifyCase]:
    out = cases
    if args.local_only:
        out = [c for c in out if "openrouter" not in c.needs]
    if args.cloud_only:
        out = [c for c in out if "openrouter" in c.needs]
    if args.mode:
        out = [c for c in out if c.mode == args.mode]
    return out


def _row(r: CaseResult) -> str:
    if r.status == "PASS":
        tail = f"{r.detail}  {render.dim(f'{r.seconds:.1f}s')}"
    elif r.status == "SKIP":
        tail = render.dim(r.detail)
    else:
        tail = render.red(r.detail)
    return f"  {render.status_label(r.status)}  {r.name:<28} {tail}"


async def cmd_verify(args) -> int:
    async with app_runtime(verbose=args.verbose) as settings:
        if args.local_only and args.cloud_only:
            from app.cli.runtime import CliError
            raise CliError("--local-only and --cloud-only are mutually exclusive")

        print(render.dim("probing services + fetching sample data..."))
        pre = await _probe(args.offline)
        pid = (await repo.create_project("_verify"))["id"]
        try:
            samples = await _stage_samples(pid, pre)
            cases = _filter(_build_cases(pid, pre, samples), args)

            results: list[CaseResult] = []
            cur_group: Optional[str] = None
            rembg_noted = False
            for case in cases:
                if not args.json and case.group != cur_group:
                    print("\n" + render.bold(case.group))
                    cur_group = case.group
                reason = _unmet(case.needs, pre)
                if reason:
                    res = CaseResult(case.group, case.name, "SKIP", reason, 0.0)
                else:
                    if not rembg_noted and case.name.startswith(("removebg", "whitebg")):
                        print(render.dim("    (rembg first run downloads its model — may take a moment)"))
                        rembg_noted = True
                    t0 = time.monotonic()
                    try:
                        detail = await case.run()
                        res = CaseResult(case.group, case.name, "PASS", detail, time.monotonic() - t0)
                    except Exception as e:  # noqa: BLE001 — any failure is a FAIL row, not a crash
                        msg = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
                        res = CaseResult(case.group, case.name, "FAIL", msg[:160], time.monotonic() - t0)
                results.append(res)
                if not args.json:
                    print(_row(res))
        finally:
            if not args.keep:
                shutil.rmtree(settings.outputs_dir / pid, ignore_errors=True)
                await repo.delete_project(pid)

        n_pass = sum(r.status == "PASS" for r in results)
        n_skip = sum(r.status == "SKIP" for r in results)
        n_fail = sum(r.status == "FAIL" for r in results)
        total = sum(r.seconds for r in results)

        if args.json:
            print(json.dumps({
                "summary": {"pass": n_pass, "skip": n_skip, "fail": n_fail, "seconds": round(total, 1)},
                "results": [r.__dict__ for r in results],
            }, ensure_ascii=False, indent=2))
        else:
            print(f"\n{render.bold('Summary')}: {render.green(f'{n_pass} PASS')} · "
                  f"{render.yellow(f'{n_skip} SKIP')} · {render.red(f'{n_fail} FAIL')}  "
                  f"({len(results)} cases, {total:.1f}s)")
            if args.keep:
                print(render.dim(f"kept verify project: {pid}"))
        return n_fail
