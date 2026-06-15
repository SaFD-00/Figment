"""산출물 다운로드/미리보기/에셋 서빙 (경로 화이트리스트 + 탈출 차단)."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

router = APIRouter(prefix="/api/jobs")

_DOWNLOAD = {
    "figure.pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "figure.svg": "image/svg+xml",
    "preview.png": "image/png",
    "spec.json": "application/json",
}
# 저장된 figure.svg에서 지연 렌더하는 래스터 산출물(고해상도/JPG)
_RASTER = {"figure.png", "figure.jpg", "preview.png"}
_RES_PX = {"1k": 1024, "2k": 2048, "4k": 4096, "8k": 8192}
_MAX_DPI = 1200  # 8K 안전 상한(메모리/시간 가드)
_SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _job_dir(request: Request, jid: str):
    store = request.app.state.store
    rec = store.load_job(jid)
    if rec is None:
        raise HTTPException(404, "job 없음")
    return store.job_dir(rec.project_id, jid), rec


def _svg_long_edge_mm(svg: str) -> float:
    m = re.search(r'width="([\d.]+)mm"\s+height="([\d.]+)mm"', svg)
    return max(float(m.group(1)), float(m.group(2))) if m else 170.0


def _target_dpi(res: str | None, dpi: int | None, svg: str) -> int:
    if dpi:
        return max(48, min(_MAX_DPI, int(dpi)))
    if res and res.lower() in _RES_PX:
        long_mm = _svg_long_edge_mm(svg) or 170.0
        return max(48, min(_MAX_DPI, round(_RES_PX[res.lower()] * 25.4 / long_mm)))
    return 192


def _render_raster(job_dir, name: str, pname: str, res, dpi, fmt) -> Response:
    """저장된 figure.svg(자기완결 임베드)에서 고해상도 PNG/JPG를 즉석 렌더."""
    from ...render.preview import png_to_jpg, svg_to_png

    svg_path = job_dir / "figure.svg"
    if not svg_path.exists():
        raise HTTPException(404, "figure.svg 없음")
    svg = svg_path.read_text("utf-8")
    want_jpg = (fmt or ("jpg" if name.endswith(".jpg") else "png")).lower() in ("jpg", "jpeg")
    png = svg_to_png(svg, dpi=_target_dpi(res, dpi, svg))
    if want_jpg:
        data, media, ext = png_to_jpg(png), "image/jpeg", "jpg"
    else:
        data, media, ext = png, "image/png", "png"
    return Response(data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{pname}.{ext}"'})


@router.get("/{jid}/files/{name}")
async def download(jid: str, name: str, request: Request,
                   res: str | None = None, dpi: int | None = None, format: str | None = None):
    job_dir, rec = _job_dir(request, jid)
    proj = request.app.state.store.load_project(rec.project_id)
    pname = (proj.name if proj else "figure").replace(" ", "_")

    # 고해상도/JPG 래스터는 figure.svg에서 지연 렌더(저장본 없이도 동작)
    want_hires = bool(res or dpi or (format and format.lower() not in ("png", "")))
    if name in _RASTER and (name != "preview.png" or want_hires):
        return _render_raster(job_dir, name, pname, res, dpi, format)

    if name not in _DOWNLOAD:
        raise HTTPException(404, "허용되지 않은 파일")
    p = job_dir / name
    if not p.exists():
        raise HTTPException(404, "파일 없음")
    ext = name.split(".")[-1]
    disp = "inline" if name == "preview.png" else "attachment"
    return FileResponse(p, media_type=_DOWNLOAD[name],
                        headers={"Content-Disposition": f'{disp}; filename="{pname}.{ext}"'})


@router.get("/{jid}/preview.svg")
async def preview_svg(jid: str, request: Request) -> Response:
    job_dir, _ = _job_dir(request, jid)
    p = job_dir / "preview.svg"
    if not p.exists():
        raise HTTPException(404, "preview 없음")
    return Response(p.read_text("utf-8"), media_type="image/svg+xml")


@router.get("/{jid}/assets/{name}")
async def asset(jid: str, name: str, request: Request) -> FileResponse:
    if not _SAFE.match(name):
        raise HTTPException(400, "잘못된 이름")
    job_dir, _ = _job_dir(request, jid)
    p = (job_dir / "assets" / name).resolve()
    if not str(p).startswith(str((job_dir / "assets").resolve())) or not p.exists():
        raise HTTPException(404, "에셋 없음")
    return FileResponse(p)


@router.get("/{jid}/thumb.png")
async def thumb(jid: str, request: Request) -> FileResponse:
    job_dir, _ = _job_dir(request, jid)
    p = job_dir / "preview.png"
    if not p.exists():
        raise HTTPException(404, "썸네일 없음")
    return FileResponse(p, media_type="image/png")
