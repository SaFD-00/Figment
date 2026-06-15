"""분야/Flowcharts 템플릿 카드 썸네일 생성 — frontend/data/templates.json 기반.

각 템플릿을 실제 생성 파이프라인(planner→spec→에셋→렌더)으로 돌려 preview.png를
``frontend/img/templates/<id>.png``에 저장한다. 갤러리(landing.js)가 이 경로를 참조하고,
없으면 CSS placeholder로 폴백한다.

- 멱등: 이미 있으면 건너뜀(--force로 재생성).
- 기본 provider=mock(오프라인 안전·placeholder 품질). 실제 figurelabs급 썸네일은
  ``--provider openrouter``(SeedReam 4.5, 이미지당 ~$0.04) + OPENROUTER_API_KEY 필요.

예) python scripts/gen_template_thumbs.py --provider openrouter
    python scripts/gen_template_thumbs.py --only bio_cells,med_anatomy --force
    python scripts/gen_template_thumbs.py --discipline biology --provider mock
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

TEMPLATES_JSON = ROOT / "frontend" / "data" / "templates.json"
OUT_DIR = ROOT / "frontend" / "img" / "templates"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)  # Google Drive 동기화 안전


async def _render_thumb(tpl: dict, provider: str, dpi: int) -> bytes:
    from figgen.assets.store import AssetStore
    from figgen.config import get_settings
    from figgen.layout.engine import LayoutEngine
    from figgen.pipeline.cli_gen import _plan
    from figgen.pipeline.planner import Planner
    from figgen.pipeline.stylist import Stylist
    from figgen.providers.registry import get_llm
    from figgen.render.exporter import export_figure
    from figgen.render.resolver import resolve
    from figgen.schema.requests import GenerationRequest

    settings = get_settings()
    planner = Planner(
        get_llm("planner", settings, provider_override=provider),
        get_llm("classifier", settings, provider_override=provider))
    req = GenerationRequest(
        description=tpl["prompt"], figure_type=tpl.get("figure_type"),
        style_preset="flat", aspect=tpl.get("aspect"), provider=provider or "auto")
    with tempfile.TemporaryDirectory() as td:
        store = AssetStore(Path(td) / "assets")
        _ft, spec = await _plan(planner, Stylist(), req, store, settings, provider)
        layout = LayoutEngine().layout(spec)
        fig = resolve(spec, layout, spec.stylesheet)
        bundle = export_figure(fig, store, preview_dpi=dpi)
    return bundle.preview_png


def _load() -> list[dict]:
    data = json.loads(TEMPLATES_JSON.read_text("utf-8"))
    return [*data.get("templates", []), *data.get("flowcharts", [])]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="템플릿 카드 썸네일 생성")
    ap.add_argument("--provider", default="mock", choices=["mock", "openrouter", "openai", "auto"])
    ap.add_argument("--force", action="store_true", help="존재해도 재생성")
    ap.add_argument("--only", default="", help="쉼표구분 id 화이트리스트")
    ap.add_argument("--discipline", default="", help="해당 분야만")
    ap.add_argument("--limit", type=int, default=0, help="최대 N개")
    ap.add_argument("--dpi", type=int, default=140, help="썸네일 DPI")
    ap.add_argument("--timeout", type=float, default=150.0,
                    help="항목당 최대 초(초과 시 실패 처리하고 다음으로). 행 방지.")
    args = ap.parse_args(argv)

    items = _load()
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        items = [t for t in items if t["id"] in wanted]
    if args.discipline:
        items = [t for t in items if t.get("discipline") == args.discipline]
    todo = [t for t in items if args.force or not (OUT_DIR / f"{t['id']}.png").exists()]
    if args.limit:
        todo = todo[: args.limit]

    if not todo:
        print("생성할 썸네일 없음(모두 존재). --force로 재생성.")
        return 0

    n_img = sum(1 for t in todo if t.get("figure_type") in ("scientific_illustration", "graphical_abstract", None))
    print(f"대상 {len(todo)}개 (이미지 생성 ~{n_img}회) · provider={args.provider} · 출력={OUT_DIR}")
    if args.provider != "mock":
        print(f"⚠ 실제 생성: 이미지 모델 호출 ~{n_img}회(비용 발생 가능). 계속합니다…")

    ok, fail = 0, 0
    for i, tpl in enumerate(todo):
        out = OUT_DIR / f"{tpl['id']}.png"
        try:
            png = asyncio.run(
                asyncio.wait_for(
                    _render_thumb(tpl, args.provider, args.dpi), timeout=args.timeout))
            _atomic_write(out, png)
            ok += 1
            print(f"  [{i + 1}/{len(todo)}] ✓ {tpl['id']}", flush=True)
        except (TimeoutError, asyncio.TimeoutError):
            fail += 1
            print(f"  [{i + 1}/{len(todo)}] ✗ {tpl['id']} — 타임아웃({args.timeout:.0f}s) 스킵",
                  flush=True)
        except Exception as e:  # noqa: BLE001
            fail += 1
            print(f"  [{i + 1}/{len(todo)}] ✗ {tpl['id']} — {e}", flush=True)
    print(f"완료: 성공 {ok} · 실패 {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
