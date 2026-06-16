"""figgen CLI — ``figgen render`` / ``figgen gen`` / ``figgen serve``.

``render``는 Phase 1(결정론 코어), ``gen``은 Phase 2(planner+mock), ``serve``는
Phase 3(웹앱)에서 채워진다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="figgen",
        description="논문용 figure를 PPTX+SVG(후편집 가능)로 생성한다.",
    )
    p.add_argument("--version", action="version", version=f"figgen {__version__}")
    sub = p.add_subparsers(dest="command", metavar="{render,gen,serve}")

    # render: spec.json → 산출물 (API 불필요)
    pr = sub.add_parser("render", help="spec.json을 SVG/PPTX/PNG로 렌더 (API 불필요)")
    pr.add_argument("spec", type=Path, help="FigureSpec JSON 경로")
    pr.add_argument("--style", default=None, help="스타일 프리셋 이름 (spec의 것을 덮어씀)")
    pr.add_argument("-o", "--out", type=Path, default=Path("figgen_out"), help="출력 디렉토리")
    pr.add_argument("--no-pptx", action="store_true", help="PPTX 생략")
    pr.add_argument("--no-png", action="store_true", help="미리보기 PNG 생략")
    pr.add_argument("--dpi", type=int, default=192, help="PNG/JPG 래스터 DPI (기본 192)")
    pr.add_argument("--format", default="png", choices=["png", "jpg"], help="래스터 포맷")
    pr.set_defaults(func=_cmd_render)

    # gen: 자연어 설명 → spec → 산출물
    pg = sub.add_parser("gen", help="설명에서 figure를 생성 (planner)")
    pg.add_argument("description", help="figure 설명 (또는 논문 메서드 텍스트)")
    pg.add_argument(
        "--type",
        dest="figure_type",
        default=None,
        choices=["method_diagram", "concept", "chart", "graphical_abstract",
                 "scientific_illustration"],
        help="figure 종류 (생략 시 자동 분류)",
    )
    pg.add_argument("--style", default="nature_minimal", help="스타일 프리셋")
    pg.add_argument(
        "--provider", default=None, choices=["mock", "openrouter", "auto"],
        help="LLM provider",
    )
    pg.add_argument(
        "--box-icons", action="store_true",
        help="method_diagram의 각 박스에 작은 일러스트 생성 (박스당 이미지 1콜)",
    )
    pg.add_argument("--dpi", type=int, default=192, help="PNG/JPG 래스터 DPI (기본 192)")
    pg.add_argument("--format", default="png", choices=["png", "jpg"], help="래스터 포맷")
    pg.add_argument("-o", "--out", type=Path, default=Path("figgen_out"), help="출력 디렉토리")
    pg.set_defaults(func=_cmd_gen)

    # serve: 웹 앱
    ps = sub.add_parser("serve", help="로컬 웹 앱 기동 + 브라우저 자동 오픈")
    ps.add_argument("--host", default=None)
    ps.add_argument("--port", type=int, default=None)
    ps.add_argument("--no-browser", action="store_true")
    ps.add_argument("--outputs", type=Path, default=None)
    ps.add_argument("--reload", action="store_true", help="개발용 자동 리로드")
    ps.set_defaults(func=_cmd_serve)

    return p


def _cmd_render(args: argparse.Namespace) -> int:
    from .render.cli_render import render_spec_file

    return render_spec_file(
        args.spec, args.out, style=args.style, want_pptx=not args.no_pptx,
        want_png=not args.no_png, dpi=args.dpi, fmt=args.format,
    )


def _cmd_gen(args: argparse.Namespace) -> int:
    from .pipeline.cli_gen import generate_cli

    return generate_cli(
        description=args.description,
        figure_type=args.figure_type,
        style=args.style,
        provider=args.provider,
        out=args.out,
        box_icons=args.box_icons,
        dpi=args.dpi,
        fmt=args.format,
    )


def _cmd_serve(args: argparse.Namespace) -> int:
    from .server.run import serve

    return serve(
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
        outputs=args.outputs,
        reload=args.reload,
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
