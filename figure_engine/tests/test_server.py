"""Phase 3 — 웹앱 API 통합 (TestClient, mock provider, 오프라인)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from figgen.server.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FIGGEN_OUTPUTS", str(tmp_path / "out"))
    monkeypatch.setenv("FIGGEN_FRONTEND", str(tmp_path / "no_fe"))  # StaticFiles 마운트 회피
    # 오프라인 테스트 — 주변 .env 키와 무관하게 mock만 활성(hermetic)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("FIGGEN_PROVIDER", "mock")
    from figgen.config import get_settings

    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def _run_job(client, pid, body, timeout=10):
    r = client.post(f"/api/projects/{pid}/jobs", json=body)
    assert r.status_code == 202
    jid = r.json()["job_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = client.get(f"/api/jobs/{jid}").json()
        if d["status"] in ("succeeded", "failed", "cancelled"):
            return jid, d
        time.sleep(0.05)
    raise AssertionError("job timeout")


def test_health_and_meta(client):
    assert client.get("/api/health").json()["status"] == "ok"
    styles = client.get("/api/meta/styles").json()
    assert {s["id"] for s in styles} >= {"nature_minimal", "neurips_pastel"}
    models = client.get("/api/meta/models").json()
    # 키 없음 → mock만 enabled
    assert any(m["id"] == "mock" and not m["disabled"] for m in models)
    assert all(m["disabled"] for m in models if m["id"] != "mock")


def test_generate_job_succeeds_and_artifacts(client):
    pid = client.post("/api/projects", json={"name": "T"}).json()["project_id"]
    jid, d = _run_job(client, pid, {
        "figure_type": "method_diagram", "prompt": "encode then decode then output",
        "style_preset": "nature_minimal", "model_prefs": {"provider": "mock"}})
    assert d["status"] == "succeeded"
    assert set(d["artifacts"]) >= {"figure.pptx", "figure.svg", "preview.png", "spec.json"}
    # 다운로드
    assert client.get(f"/api/jobs/{jid}/files/figure.pptx").content[:2] == b"PK"
    assert "svg" in client.get(f"/api/jobs/{jid}/preview.svg").headers["content-type"]
    assert client.get(f"/api/jobs/{jid}/spec").json()["figure_type"] == "method_diagram"


def test_sse_replay_after_completion(client):
    pid = client.post("/api/projects", json={"name": "T"}).json()["project_id"]
    jid, _ = _run_job(client, pid, {
        "figure_type": "concept", "prompt": "brain to model to result",
        "model_prefs": {"provider": "mock"}})
    # 완료 후 접속 → 저장된 이벤트 리플레이 (done 포함)
    types = []
    with client.stream("GET", f"/api/jobs/{jid}/events") as s:
        for line in s.iter_lines():
            if line.startswith("event:"):
                types.append(line.split(":", 1)[1].strip())
            if "done" in types:
                break
    assert "stage" in types and "done" in types


def test_concept_generates_asset(client):
    pid = client.post("/api/projects", json={"name": "T"}).json()["project_id"]
    jid, d = _run_job(client, pid, {
        "figure_type": "concept", "prompt": "a brain connected to a model",
        "model_prefs": {"provider": "mock"}})
    spec = client.get(f"/api/jobs/{jid}/spec").json()
    # ImageElement에 asset_id가 바인딩되고 에셋이 서빙됨
    ids = []
    def walk(n):
        if n.get("type") == "image" and n.get("asset_id"):
            ids.append(n["asset_id"])
        for c in n.get("children", []):
            walk(c)
        for it in n.get("items", []):
            walk(it["node"])
    walk(spec["root"])
    assert ids
    assert client.get(f"/api/jobs/{jid}/assets/{ids[0]}.png").content[:4] == b"\x89PNG"


def test_versions_and_parent_chain(client):
    pid = client.post("/api/projects", json={"name": "T"}).json()["project_id"]
    jid, _ = _run_job(client, pid, {
        "figure_type": "method_diagram", "prompt": "a then b",
        "model_prefs": {"provider": "mock"}})
    # 부분 재생성(부모 체인)
    jid2, d2 = _run_job(client, pid, {
        "figure_type": "method_diagram", "prompt": "a then b",
        "model_prefs": {"provider": "mock"}, "parent_job_id": jid,
        "edit": {"mode": "global", "instruction": "make it wider", "target_element_ids": []}})
    assert d2["status"] == "succeeded"
    versions = client.get(f"/api/projects/{pid}/versions").json()
    assert len(versions) == 2
    child = next(v for v in versions if v["job_id"] == jid2)
    assert child["parent_job_id"] == jid


def test_export_highres_and_jpg(client):
    """CS-5: figure.svg에서 고해상도 PNG/JPG를 지연 렌더해 다운로드."""
    from io import BytesIO

    from PIL import Image

    pid = client.post("/api/projects", json={"name": "T"}).json()["project_id"]
    jid, _ = _run_job(client, pid, {
        "figure_type": "method_diagram", "prompt": "a then b",
        "model_prefs": {"provider": "mock"}})
    base = client.get(f"/api/jobs/{jid}/files/preview.png").content
    big = client.get(f"/api/jobs/{jid}/files/figure.png?res=4k")
    assert big.status_code == 200 and big.content[:4] == b"\x89PNG"
    assert max(Image.open(BytesIO(big.content)).size) > max(Image.open(BytesIO(base)).size)
    jpg = client.get(f"/api/jobs/{jid}/files/figure.jpg?res=1k")
    assert jpg.status_code == 200 and jpg.content[:2] == b"\xff\xd8"  # JPEG SOI


def test_upload_data_file(client):
    pid = client.post("/api/projects", json={"name": "T"}).json()["project_id"]
    r = client.post(f"/api/projects/{pid}/uploads",
                    files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")}, data={"kind": "data"})
    assert r.status_code == 200
    assert r.json()["file_id"].startswith("f_")
