"""Phase D — figurelabs surface(sketch/refine/vectorize + 인-캔버스 canvas_op) 통합 (오프라인/mock)."""

from __future__ import annotations

import io
import json
import time

import pytest
from fastapi.testclient import TestClient

from figgen.server.app import create_app


def _png(w: int = 64, h: int = 48, color: tuple[int, int, int] = (80, 120, 200)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FIGGEN_OUTPUTS", str(tmp_path / "out"))
    monkeypatch.setenv("FIGGEN_FRONTEND", str(tmp_path / "no_fe"))
    monkeypatch.setenv("OPENAI_API_KEY", "")  # mock only (hermetic)
    monkeypatch.setenv("FIGGEN_PROVIDER", "mock")
    from figgen.config import get_settings

    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def _project(client) -> str:
    return client.post("/api/projects", json={"name": "T"}).json()["project_id"]


def _run(client, pid, body, timeout=20):
    r = client.post(f"/api/projects/{pid}/jobs", json=body)
    assert r.status_code == 202, r.text
    jid = r.json()["job_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = client.get(f"/api/jobs/{jid}").json()
        if d["status"] in ("succeeded", "failed", "cancelled"):
            return jid, d
        time.sleep(0.05)
    raise AssertionError("job timeout")


def _upload(client, pid, kind="reference") -> str:
    r = client.post(f"/api/projects/{pid}/uploads",
                    files={"file": ("img.png", _png(), "image/png")}, data={"kind": kind})
    assert r.status_code == 200, r.text
    return r.json()["file_id"]


def _walk_ids(node, pred):
    if isinstance(node, dict):
        if pred(node) and "id" in node:
            yield node["id"]
        for v in node.values():
            yield from _walk_ids(v, pred)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_ids(v, pred)


def test_vectorize_task_produces_svg(client):
    pid = _project(client)
    fid = _upload(client, pid)
    jid, d = _run(client, pid, {"task": "vectorize", "reference_image_ids": [fid]})
    assert d["status"] == "succeeded", d
    svg = client.get(f"/api/jobs/{jid}/files/figure.svg")
    assert svg.status_code == 200 and "<svg" in svg.text


def test_refine_task_succeeds(client):
    pid = _project(client)
    fid = _upload(client, pid)
    jid, d = _run(client, pid, {"task": "refine", "reference_image_ids": [fid],
                                "refine_modes": ["upscale", "denoise"]})
    assert d["status"] == "succeeded", d
    assert client.get(f"/api/jobs/{jid}/files/preview.png").status_code == 200


def test_sketch_task_succeeds(client):
    pid = _project(client)
    fid = _upload(client, pid)
    jid, d = _run(client, pid, {"task": "sketch", "prompt": "cell diagram from this sketch",
                                "reference_image_ids": [fid]})
    assert d["status"] == "succeeded", d


def test_canvas_text_edit_changes_label_deterministically(client):
    pid = _project(client)
    jid, d = _run(client, pid, {"task": "generate", "figure_type": "method_diagram",
                                "prompt": "encode then decode then output"})
    assert d["status"] == "succeeded", d
    spec = client.get(f"/api/jobs/{jid}/spec").json()
    box_id = next(_walk_ids(spec["root"], lambda n: n.get("type") == "box"))
    cid, d2 = _run(client, pid, {"task": "edit", "parent_job_id": jid,
                                 "canvas_op": {"kind": "text_edit", "target_element_id": box_id,
                                               "text": "ENCODER-X"}})
    assert d2["status"] == "succeeded", d2
    spec2 = client.get(f"/api/jobs/{cid}/spec").json()
    assert "ENCODER-X" in json.dumps(spec2)


def test_canvas_region_redraw_on_scene_image(client):
    pid = _project(client)
    jid, d = _run(client, pid, {"task": "generate", "figure_type": "scientific_illustration",
                                "prompt": "a single neuron with dendrites"})
    assert d["status"] == "succeeded", d
    spec = client.get(f"/api/jobs/{jid}/spec").json()
    img_id = next(_walk_ids(spec["root"],
                            lambda n: n.get("type") == "image" and n.get("asset_id")))
    base_asset = next(n["asset_id"] for n in _iter_nodes(spec["root"])
                      if n.get("id") == img_id)
    cid, d2 = _run(client, pid, {"task": "edit", "parent_job_id": jid,
                                 "canvas_op": {"kind": "region_redraw", "target_element_id": img_id,
                                               "instruction": "add a longer axon",
                                               "region": [0.1, 0.1, 0.4, 0.4]}})
    assert d2["status"] == "succeeded", d2
    spec2 = client.get(f"/api/jobs/{cid}/spec").json()
    new_asset = next(n["asset_id"] for n in _iter_nodes(spec2["root"])
                     if n.get("id") == img_id)
    assert new_asset != base_asset  # region redraw가 새 asset 버전을 만든다


def test_canvas_white_bg_on_scene_image(client):
    pid = _project(client)
    jid, d = _run(client, pid, {"task": "generate", "figure_type": "graphical_abstract",
                                "prompt": "graphical abstract of photosynthesis"})
    assert d["status"] == "succeeded", d
    spec = client.get(f"/api/jobs/{jid}/spec").json()
    img_id = next(_walk_ids(spec["root"],
                            lambda n: n.get("type") == "image" and n.get("asset_id")))
    cid, d2 = _run(client, pid, {"task": "edit", "parent_job_id": jid,
                                 "canvas_op": {"kind": "white_bg", "target_element_id": img_id}})
    assert d2["status"] == "succeeded", d2


def _iter_nodes(node):
    if isinstance(node, dict):
        if "type" in node:
            yield node
        for v in node.values():
            yield from _iter_nodes(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_nodes(v)
