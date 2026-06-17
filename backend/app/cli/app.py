"""`figment` CLI entry point — argparse parser + async dispatch.

Run as `python -m app.cli ...` (or via the `scripts/figment` wrapper). Every subcommand boots the
in-process backend (see runtime.app_runtime) and reuses the same engine the web app does.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from app.cli import commands, render, verify
from app.cli.runtime import CliError

__version__ = "0.1.0"

_MODES = ["txt2img", "img2img", "inpaint", "edit", "controlnet", "reference"]
_CONTROL = ["canny", "depth", "scribble", "lineart"]


def build_parser() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("-v", "--verbose", action="store_true", help="show INFO logs on stderr")

    p = argparse.ArgumentParser(prog="figment", description="Figment — in-process terminal CLI (no server needed).")
    p.add_argument("--version", action="version", version=f"figment {__version__}")
    sub = p.add_subparsers(dest="command", metavar="<command>")

    # generate
    g = sub.add_parser("generate", parents=[parent], help="generate/edit an image (all 6 modes)")
    g.add_argument("prompt", nargs="?", default="", help="prompt text (positional)")
    g.add_argument("--mode", choices=_MODES, default="txt2img")
    g.add_argument("--model", help="image model id (see: figment models); default by mode")
    g.add_argument("--prompt", dest="prompt", help="prompt text (overrides positional)")
    g.add_argument("--negative", help="negative prompt (SDXL/Pony)")
    g.add_argument("--width", type=int, default=1024)
    g.add_argument("--height", type=int, default=1024)
    g.add_argument("--steps", type=int, default=None)
    g.add_argument("--cfg", type=float, default=None)
    g.add_argument("--seed", type=int, default=None)
    g.add_argument("--batch", type=int, default=1)
    g.add_argument("--denoise", type=float, default=0.6)
    g.add_argument("--source", help="source image path (img2img/inpaint/edit)")
    g.add_argument("--mask", help="mask image path (inpaint)")
    g.add_argument("--ref", action="append", help="reference image path (repeatable)")
    g.add_argument("--controlnet-type", dest="controlnet_type", choices=_CONTROL, default=None)
    g.add_argument("--strength", type=float, default=0.7, help="controlnet strength")
    g.add_argument("--upscale", action="store_true", help="Real-ESRGAN upscale the result (post-step)")
    g.add_argument("--remove-bg", dest="remove_bg", action="store_true")
    g.add_argument("--llm-model", dest="llm_model", help="planner LLM id (cloud/figure path)")
    g.add_argument("--project", help="project id (default: a reused 'cli' project)")
    g.add_argument("--out", help="copy the result to this path")
    g.add_argument("--no-progress", dest="no_progress", action="store_true")
    g.set_defaults(func=commands.cmd_generate)

    # enhance
    e = sub.add_parser("enhance", parents=[parent], help="rewrite a short idea into a rich English prompt")
    e.add_argument("prompt", help="short idea (any language)")
    e.add_argument("--instruction", help="optional 'how to enhance' guidance")
    e.add_argument("--llm-model", dest="llm_model")
    e.add_argument("--image-model", dest="image_model", help="target image model (tags vs prose hint)")
    e.add_argument("--image", help="image path to ground a vision LLM enhance")
    e.set_defaults(func=commands.cmd_enhance)

    # post-ops
    for name, fn, helptext in [
        ("upscale", commands.cmd_upscale, "Real-ESRGAN upscale an image file"),
        ("removebg", commands.cmd_removebg, "remove background (transparent)"),
        ("whitebg", commands.cmd_whitebg, "remove background onto white"),
    ]:
        sp = sub.add_parser(name, parents=[parent], help=helptext)
        sp.add_argument("image", help="input image path")
        sp.add_argument("--out", help="output path (default: alongside input)")
        sp.set_defaults(func=fn)

    # export
    x = sub.add_parser("export", parents=[parent], help="export an asset to png/svg/pptx")
    x.add_argument("asset_id", help="asset id (see: figment projects <pid>)")
    x.add_argument("--fmt", choices=["png", "svg", "pptx"], default="png")
    x.add_argument("--out", help="output path")
    x.set_defaults(func=commands.cmd_export)

    # chat
    c = sub.add_parser("chat", parents=[parent], help="one-shot chat with the planner LLM (+GENSPEC)")
    c.add_argument("message", help="your message")
    c.add_argument("--project", help="project id for multi-turn history")
    c.add_argument("--llm-model", dest="llm_model")
    c.add_argument("--json", action="store_true", help="emit {text, genspec} as JSON")
    c.set_defaults(func=commands.cmd_chat)

    # models
    m = sub.add_parser("models", parents=[parent], help="list image + LLM models with readiness")
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=commands.cmd_models)

    # projects
    pr = sub.add_parser("projects", parents=[parent], help="list projects, or a project's assets")
    pr.add_argument("project_id", nargs="?", help="project id → list its assets")
    pr.add_argument("--json", action="store_true")
    pr.set_defaults(func=commands.cmd_projects)

    # doctor
    d = sub.add_parser("doctor", parents=[parent], aliases=["health"],
                       help="check services, keys, and per-model readiness")
    d.add_argument("--strict", action="store_true", help="exit nonzero if anything is not ready")
    d.set_defaults(func=commands.cmd_doctor)

    # verify
    v = sub.add_parser("verify", parents=[parent],
                       help="run every pipeline (local+cloud) → PASS/SKIP/FAIL matrix")
    v.add_argument("--local-only", dest="local_only", action="store_true", help="skip cloud (OpenRouter) cases")
    v.add_argument("--cloud-only", dest="cloud_only", action="store_true", help="only cloud (OpenRouter) cases")
    v.add_argument("--mode", choices=_MODES, help="only image cases of this mode")
    v.add_argument("--offline", action="store_true", help="skip net-dependent cases (use cached samples only)")
    v.add_argument("--keep", action="store_true", help="keep generated verify artifacts + project")
    v.add_argument("--json", action="store_true", help="emit the matrix as JSON")
    v.set_defaults(func=verify.cmd_verify)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return asyncio.run(args.func(args))
    except CliError as e:
        print(render.red(f"error: {e}"), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
