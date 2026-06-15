#!/usr/bin/env python
"""산출물 감사 — spec 풍부도 + PPTX/SVG 후편집성(3-키 계약)을 정량 검증. LLM 불필요.

    python scripts/audit_artifacts.py <out_dir> [<out_dir> ...]

각 디렉토리의 spec.json / figure.svg / figure.pptx 를 읽어:
  - spec: 요소 수, type/shape/role 분포, 중첩 깊이, 커넥터 수+line_role
  - SVG: <text> 벡터 수, data-fg-id 수, marker(화살촉) 수
  - PPTX: fg-* 도형명 수, 텍스트 프레임(<a:t>) 수, 커넥터(<p:cxnSp>) 수
  - 3-키 정합: spec id ⊆ SVG data-fg-id, spec id ⊆ PPTX fg-name (시각 요소 한정)
JSON 한 줄로 출력.
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

_CONTAINER = {"row", "column", "grid", "group", "free"}
_VISUAL_LEAF = {"box", "text", "image", "chart"}


def _walk(node: dict, depth: int, acc: dict) -> None:
    acc["depth"] = max(acc["depth"], depth)
    t = node.get("type")
    acc["types"][t] += 1
    nid = node.get("id")
    if nid:
        acc["ids"].append(nid)
        if t in _VISUAL_LEAF or t == "group":
            acc["visual_ids"].add(nid)
    if node.get("shape"):
        acc["shapes"][node["shape"]] += 1
    if node.get("role"):
        acc["roles"][node["role"]] += 1
    for c in node.get("children", []):
        _walk(c, depth + 1, acc)
    for it in node.get("items", []):
        _walk(it.get("node", {}), depth + 1, acc)


def audit(d: Path) -> dict:
    out: dict = {"dir": str(d)}
    spec = json.loads((d / "spec.json").read_text("utf-8"))
    acc = {"depth": 0, "types": Counter(), "shapes": Counter(), "roles": Counter(),
           "ids": [], "visual_ids": set()}
    _walk(spec["root"], 0, acc)
    conns = spec.get("connectors", [])
    out["figure_type"] = spec.get("figure_type")
    out["title"] = spec.get("title")
    out["spec"] = {
        "elements": len(acc["ids"]),
        "depth": acc["depth"],
        "types": dict(acc["types"]),
        "shapes": dict(acc["shapes"]),
        "roles": dict(acc["roles"]),
        "connectors": len(conns),
        "connector_roles": dict(Counter(c.get("line_role") for c in conns)),
        "labeled_connectors": sum(1 for c in conns if c.get("label")),
    }

    svg = (d / "figure.svg").read_text("utf-8")
    svg_ids = set(re.findall(r'data-fg-id="([^"]+)"', svg))
    out["svg"] = {
        "text_elements": svg.count("<text"),
        "data_fg_ids": len(svg_ids),
        "markers": svg.count("<marker"),
        "bytes": len(svg),
    }

    pptx_xml = ""
    with zipfile.ZipFile(d / "figure.pptx") as z:
        slides = sorted(n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml", n))
        if slides:
            pptx_xml = z.read(slides[0]).decode("utf-8")
    fg_names = set(re.findall(r'name="(fg-[^"]+)"', pptx_xml))
    out["pptx"] = {
        "fg_shape_names": len(fg_names),
        "text_runs": pptx_xml.count("<a:t>"),
        "connectors": pptx_xml.count("<p:cxnSp"),
        "shapes": pptx_xml.count("<p:sp>"),
        "pictures": pptx_xml.count("<p:pic>"),
    }

    # 3-키 정합: 시각 요소 id 가 SVG/PPTX 양쪽에 존재하는가
    vis = acc["visual_ids"]
    pptx_ids = {n[3:] for n in fg_names}  # "fg-" 제거
    out["contract"] = {
        "visual_ids": len(vis),
        "in_svg": len(vis & svg_ids),
        "in_pptx": len(vis & pptx_ids),
        "missing_in_svg": sorted(vis - svg_ids)[:10],
        "missing_in_pptx": sorted(vis - pptx_ids)[:10],
        "svg_ok": vis <= svg_ids,
        "pptx_ok": vis <= pptx_ids,
    }
    # 편집성 게이트: 텍스트가 이미지가 아니라 실제 <a:t>/<text> 로 존재
    out["editable"] = bool(out["pptx"]["text_runs"] > 0 and out["svg"]["text_elements"] > 0)
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: audit_artifacts.py <out_dir> [...]", file=sys.stderr)
        return 2
    for a in argv:
        d = Path(a)
        try:
            print(json.dumps(audit(d), ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"dir": a, "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
