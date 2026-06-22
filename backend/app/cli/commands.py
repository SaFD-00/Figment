"""CLI subcommand implementations — each mirrors a web feature and reuses the backend directly.

Generation goes through `run_genspec` (same worker as /jobs). Post-ops reuse `orchestrator.pipeline`
and `rembg`. Export mirrors the /assets/{id}/export route. Enhance/chat reuse the LLM routing and
message builders. None of this needs a running uvicorn server.
"""
from __future__ import annotations

import asyncio
import base64
import json
import shutil
import sys
from pathlib import Path

from app import deps
from app.cli import render
from app.cli.runtime import CliError, app_runtime, ensure_cli_project, run_genspec, stage_image_asset
from app.comfy.templates import validate_required_nodes
from app.db import repo
from app.engines import model_ready
from app.engines.cloud import cloud_key_present
from app.llm.handoff import GenSpecExtractor
from app.llm.prompts import build_enhance_messages, build_messages
from app.llm.routing import chat_stream
from app.models_catalog.registry import LLM_MODELS, MODELS, ModelDef
from app.orchestrator import pipeline
from app.schemas.genspec import GenSpec, Mode, ReferenceImage
from app.services import export_ops, storage


def _serialize_model(m: ModelDef) -> dict:
    return {
        "id": m.id, "label": m.label, "kind": m.kind, "engine": m.engine,
        "provider": m.provider, "modes": [mode.value for mode in m.supports],
        "vision": m.vision, "nsfw": m.nsfw, "ready": model_ready(m),
    }


# ── generate ────────────────────────────────────────────────────────────────────
async def cmd_generate(args) -> int:
    async with app_runtime(verbose=args.verbose):
        if args.model and args.model not in MODELS:
            raise CliError(f"unknown model '{args.model}'. See: figment models")
        pid = args.project or await ensure_cli_project()
        if args.project and not await repo.get_project(pid):
            raise CliError(f"project not found: {pid}")

        source_asset = await stage_image_asset(pid, args.source, "source") if args.source else None
        mask_asset = await stage_image_asset(pid, args.mask, "mask") if args.mask else None
        refs = [ReferenceImage(asset=await stage_image_asset(pid, r, "reference")) for r in (args.ref or [])]

        try:
            spec = GenSpec(
                mode=Mode(args.mode), model=args.model,
                prompt=args.prompt or "", negative_prompt=args.negative or "",
                width=args.width, height=args.height, steps=args.steps, cfg=args.cfg,
                seed=args.seed, batch=args.batch, denoise=args.denoise,
                source_asset=source_asset, mask_asset=mask_asset, reference_images=refs,
                controlnet_type=args.controlnet_type, controlnet_strength=args.strength,
                upscale=False, remove_bg=args.remove_bg, llm_model=args.llm_model,
            )
        except ValueError as e:
            raise CliError(f"invalid request: {e}") from e

        asset = await run_genspec(spec, project_id=pid, show_progress=not args.no_progress)
        out_path = asset["path"]

        if args.upscale:  # the worker does not chain upscale — apply it here (like /assets/{id}/upscale)
            data = Path(asset["path"]).read_bytes()
            up = await pipeline.upscale_image(deps.comfy(), data)
            p, w, h = storage.save_image(pid, up, "upscaled")
            asset = await repo.create_asset(pid, "upscaled", p, w, h, parent_id=asset["id"])
            out_path = asset["path"]

        if args.out:
            shutil.copyfile(out_path, args.out)
            out_path = args.out

        print(render.dim(f"asset {asset['id']}  ({asset.get('width')}x{asset.get('height')})"), file=sys.stderr)
        print(out_path)  # stdout: the final image path (pipeable)
        return 0


# ── prompt enhance ───────────────────────────────────────────────────────────────
async def cmd_enhance(args) -> int:
    from app.routers.prompt import EnhanceRequest, _clean, _enhance_image_url  # reuse route logic

    text = (args.prompt or "").strip()
    if not text:
        raise CliError("prompt is empty")
    async with app_runtime(verbose=args.verbose):
        image_b64 = base64.b64encode(Path(args.image).read_bytes()).decode("ascii") if args.image else None
        req = EnhanceRequest(prompt=text, llm_model=args.llm_model, image_model=args.image_model,
                             instruction=args.instruction, image=image_b64)
        messages = build_enhance_messages(text, req.image_model, instruction=req.instruction,
                                           image_url=_enhance_image_url(req))
        try:
            chunks = [tok async for tok in chat_stream(messages, req.llm_model)]
        except Exception as e:  # noqa: BLE001
            raise CliError(f"enhance failed: {e}") from e
        enhanced = _clean("".join(chunks))
        if not enhanced:
            raise CliError("the LLM returned an empty result")
        print(enhanced)  # stdout only — pipe straight into `generate --prompt "$(...)"`
        return 0


# ── post-ops (operate on a raw image file; no project/job) ───────────────────────
async def _postop(args, fn_name: str, suffix: str) -> int:
    src = Path(args.image)
    if not src.exists():
        raise CliError(f"file not found: {src}")
    async with app_runtime(verbose=args.verbose):
        data = src.read_bytes()
        if fn_name == "upscale":
            out = await pipeline.upscale_image(deps.comfy(), data)
        elif fn_name == "remove_bg":
            out = await pipeline.remove_bg(data)
        else:
            out = await pipeline.white_bg(data)
        dst = Path(args.out) if args.out else src.with_suffix(f".{suffix}.png")
        dst.write_bytes(out)
        print(str(dst))
        return 0


async def cmd_upscale(args) -> int:  return await _postop(args, "upscale", "upscaled")
async def cmd_removebg(args) -> int: return await _postop(args, "remove_bg", "nobg")
async def cmd_whitebg(args) -> int:  return await _postop(args, "white_bg", "whitebg")


# ── export ───────────────────────────────────────────────────────────────────────
async def cmd_export(args) -> int:
    async with app_runtime(verbose=args.verbose):
        a = await repo.get_asset(args.asset_id)
        if not a:
            raise CliError(f"asset not found: {args.asset_id}")
        fmt = args.fmt.lower()
        meta = a.get("meta") or {}
        dst = Path(args.out) if args.out else Path(f"figment_{a['id']}.{fmt}")

        if fmt == "png":
            if not Path(a["path"]).exists():
                raise CliError("asset file missing on disk")
            shutil.copyfile(a["path"], dst)
        elif fmt == "svg":
            sidecar = meta.get("svg")
            if sidecar and Path(sidecar).exists():
                shutil.copyfile(sidecar, dst)
            else:
                png = Path(a["path"]).read_bytes()
                dst.write_text(await asyncio.to_thread(export_ops.png_to_svg, png), encoding="utf-8")
        elif fmt == "pptx":
            sidecar = meta.get("pptx")
            if sidecar and Path(sidecar).exists():
                shutil.copyfile(sidecar, dst)
            else:
                png = Path(a["path"]).read_bytes()
                dst.write_bytes(await asyncio.to_thread(export_ops.png_to_pptx, png))
        else:
            raise CliError(f"unsupported format: {fmt}")
        print(str(dst))
        return 0


# ── chat (one-shot) ──────────────────────────────────────────────────────────────
async def cmd_chat(args) -> int:
    async with app_runtime(verbose=args.verbose):
        pid = args.project or await ensure_cli_project("cli-chat")
        if args.project and not await repo.get_project(pid):
            raise CliError(f"project not found: {pid}")
        history = await repo.list_messages(pid)
        await repo.add_message(pid, "user", args.message)
        messages = build_messages(history, args.message)

        extractor = GenSpecExtractor()
        visible = ""
        try:
            async for tok in chat_stream(messages, args.llm_model):
                slice_ = extractor.feed(tok)
                if slice_:
                    visible += slice_
                    if not args.json:
                        sys.stdout.write(slice_)
                        sys.stdout.flush()
        except Exception as e:  # noqa: BLE001
            raise CliError(f"chat failed: {e}") from e
        tail = extractor.trailing_visible()
        if tail:
            visible += tail
            if not args.json:
                sys.stdout.write(tail)
        spec, _raw, err = extractor.finish()
        spec_dict = spec.model_dump(mode="json") if spec else None
        await repo.add_message(pid, "assistant", visible.strip(), genspec=spec_dict)

        if args.json:
            print(json.dumps({"text": visible.strip(), "genspec": spec_dict, "error": err}, ensure_ascii=False, indent=2))
        else:
            print()
            if spec_dict:
                print(render.cyan("\n── GENSPEC (run: figment generate ...) ──"))
                print(json.dumps(spec_dict, ensure_ascii=False, indent=2))
            elif err:
                print(render.yellow(f"(GENSPEC parse note: {err})"), file=sys.stderr)
        return 0


# ── catalogs & status ────────────────────────────────────────────────────────────
async def cmd_models(args) -> int:
    async with app_runtime(verbose=args.verbose):
        image = [_serialize_model(m) for m in MODELS.values()]
        llm = [_serialize_model(m) for m in LLM_MODELS.values()]
        if args.json:
            print(json.dumps({"image": image, "llm": llm}, ensure_ascii=False, indent=2))
            return 0
        def rows(items):
            return [[m["id"], m["engine"], ",".join(m["modes"]) or "-",
                     render.green("ready") if m["ready"] else render.yellow("not ready")] for m in items]
        print(render.bold("IMAGE models"))
        print(render.table(["id", "engine", "modes", "status"], rows(image)))
        print("\n" + render.bold("LLM models"))
        print(render.table(["id", "engine", "modes", "status"], rows(llm)))
        return 0


async def cmd_projects(args) -> int:
    async with app_runtime(verbose=args.verbose):
        if args.project_id:
            assets = await repo.list_assets(args.project_id)
            if args.json:
                print(json.dumps(assets, ensure_ascii=False, indent=2, default=str))
                return 0
            rows = [[a["id"], a["kind"], f"{a.get('width')}x{a.get('height')}",
                     "ok" if Path(a["path"]).exists() else render.red("missing")] for a in assets]
            print(render.table(["asset", "kind", "size", "file"], rows))
        else:
            projects = await repo.list_projects()
            if args.json:
                print(json.dumps(projects, ensure_ascii=False, indent=2, default=str))
                return 0
            rows = [[p["id"], p["title"], p.get("cover_asset") or "-"] for p in projects]
            print(render.table(["project", "title", "cover"], rows))
        return 0


async def cmd_doctor(args) -> int:
    from app.config import get_settings
    async with app_runtime(verbose=args.verbose) as s:
        comfy_ok = await deps.comfy().ping()
        nodes = await validate_required_nodes(deps.comfy()) if comfy_ok else None
        ver = await deps.ollama().version()
        tags = await deps.ollama().installed_models() if ver else []
        ollama_tag = get_settings().ollama_llm
        ollama_has = ollama_tag in tags
        or_key = cloud_key_present("openrouter")

        print(render.bold("Services"))
        print(f"  ComfyUI   : {render.green('reachable') if comfy_ok else render.red('unreachable')}  {render.dim(s.comfy_url)}")
        if nodes is not None and not nodes.get("ok"):
            print(render.yellow(f"    missing core nodes: {nodes.get('missing')}"))
        if nodes is not None and nodes.get("missing_optional"):
            print(render.dim(f"    optional nodes absent: {nodes['missing_optional']}"))
        print(f"  Ollama    : {render.green(ver) if ver else render.red('unreachable')}  {render.dim(s.ollama_url)}"
              f"  ({'has' if ollama_has else render.yellow('missing')} {ollama_tag})")
        print(f"  OpenRouter: {render.green('key set') if or_key else render.yellow('no OPENROUTER_API_KEY')}")

        print("\n" + render.bold("Model readiness"))
        rows = [[m.id, m.engine, render.green("ready") if model_ready(m) else render.yellow("not ready")]
                for m in list(MODELS.values()) + list(LLM_MODELS.values())]
        print(render.table(["id", "engine", "status"], rows))

        if args.strict:
            all_ready = comfy_ok and bool(ver) and all(model_ready(m) for m in MODELS.values())
            return 0 if all_ready else 1
        return 0
