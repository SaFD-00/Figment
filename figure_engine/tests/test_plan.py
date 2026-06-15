"""M6 — 대화형 계획 확정(/plan) + 합의→생성 (TestClient, mock provider, 오프라인)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from figgen.server.app import create_app

# 1x1 PNG (투명)
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f9f0000000049454e44ae426082")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FIGGEN_OUTPUTS", str(tmp_path / "out"))
    monkeypatch.setenv("FIGGEN_FRONTEND", str(tmp_path / "no_fe"))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("FIGGEN_PROVIDER", "mock")
    from figgen.config import get_settings

    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def _pid(client):
    return client.post("/api/projects", json={"name": "T"}).json()["project_id"]


def _plan(client, pid, messages, **extra):
    body = {"messages": messages, "model_prefs": {"provider": "mock"}, **extra}
    r = client.post(f"/api/projects/{pid}/plan", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_plan_requires_messages(client):
    pid = _pid(client)
    r = client.post(f"/api/projects/{pid}/plan", json={"messages": []})
    assert r.status_code == 400


def test_plan_text_is_ready_with_brief(client):
    pid = _pid(client)
    turn = _plan(client, pid, [{"role": "user", "content": "대식세포가 박테리아를 포식하는 면역 반응 단계"}])
    assert turn["ready"] is True
    plan = turn["plan"]
    assert plan["task"] == "generate"
    assert plan["figure_type"] == "scientific_illustration"
    assert plan["reference_role"] == "none"
    assert plan["description"]
    assert turn["reply"]


def test_plan_chart_intent(client):
    pid = _pid(client)
    turn = _plan(client, pid, [{"role": "user", "content": "이 측정값을 막대 그래프 chart 로 그려줘"}])
    assert turn["plan"]["figure_type"] == "chart"


def test_plan_image_routes_to_refine(client):
    pid = _pid(client)
    up = client.post(f"/api/projects/{pid}/uploads",
                     files={"file": ("fig.png", _PNG, "image/png")}, data={"kind": "reference"})
    fid = up.json()["file_id"]
    turn = _plan(client, pid, [{"role": "user", "content": "이 figure를 업스케일 정제해줘"}],
                 reference_image_ids=[fid])
    plan = turn["plan"]
    assert plan["task"] == "refine"
    assert plan["reference_role"] == "refine"
    assert "upscale" in plan["refine_modes"]


def test_plan_image_routes_to_sketch(client):
    pid = _pid(client)
    up = client.post(f"/api/projects/{pid}/uploads",
                     files={"file": ("s.png", _PNG, "image/png")}, data={"kind": "reference"})
    fid = up.json()["file_id"]
    turn = _plan(client, pid, [{"role": "user", "content": "이 손스케치를 깔끔한 figure로 만들어줘"}],
                 reference_image_ids=[fid])
    assert turn["plan"]["task"] == "sketch"
    assert turn["plan"]["reference_role"] == "sketch"


def test_confirmed_plan_generates_figure(client):
    """대화 확정 → 그 PlanBrief로 기존 /jobs 호출이 성공해야 한다(엔드투엔드)."""
    pid = _pid(client)
    turn = _plan(client, pid, [{"role": "user", "content": "encode then decode then output 파이프라인"}])
    plan = turn["plan"]
    r = client.post(f"/api/projects/{pid}/jobs", json={
        "task": plan["task"], "figure_type": plan["figure_type"], "prompt": plan["description"],
        "model_prefs": {"provider": "mock"}})
    assert r.status_code == 202
    jid = r.json()["job_id"]
    deadline = time.time() + 10
    while time.time() < deadline:
        d = client.get(f"/api/jobs/{jid}").json()
        if d["status"] in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(0.05)
    assert d["status"] == "succeeded"
    assert set(d["artifacts"]) >= {"figure.svg", "figure.pptx", "spec.json"}


# ── 스타일 참조 이미지 반영(reference_role="style") ────────────────────────────
def test_style_guidance_helpers():
    from figgen.pipeline.planner import RefStyleReport, _style_guidance, _with_style

    assert _style_guidance(None) == ""
    assert _with_style("base", None) == "base"
    rep = RefStyleReport(palette_hex=["#AABBCC", "#112233"], density="dense",
                         layout_pattern="grid", font_feel="serif")
    guidance = _style_guidance(rep)
    assert "#AABBCC" in guidance and "dense" in guidance
    assert "grid" in guidance and "serif" in guidance
    out = _with_style("base prompt", rep)
    assert out.startswith("base prompt") and "#AABBCC" in out


def test_build_scene_prompt_includes_palette():
    from figgen.assets.prompts import build_scene_prompt

    sp = build_scene_prompt("a cell", "nature_minimal", palette=["#AABBCC", "#445566"])
    assert "#AABBCC" in sp


def test_generate_scene_spec_threads_style_palette(tmp_path, monkeypatch):
    """style_ref가 있으면 베이스 이미지 생성 프롬프트에 참조 팔레트가 포함돼야 한다(배선 검증)."""
    import asyncio
    import io

    from PIL import Image

    from figgen.assets.store import AssetStore
    from figgen.config import get_settings
    from figgen.pipeline import scene as scene_mod
    from figgen.pipeline.planner import Planner, RefStyleReport
    from figgen.providers import MockLLMClient
    from figgen.schema.requests import GenerationRequest

    captured: dict[str, str] = {}

    async def _fake_base(prompt, client, *, width_px, height_px):
        captured["prompt"] = prompt
        buf = io.BytesIO()
        Image.new("RGBA", (width_px, height_px), (255, 255, 255, 255)).save(buf, format="PNG")
        return buf.getvalue()

    monkeypatch.setattr(scene_mod, "generate_base_image", _fake_base)
    store = AssetStore(tmp_path / "assets")
    req = GenerationRequest(description="immune response scene", provider="mock")
    rep = RefStyleReport(palette_hex=["#3C5488", "#E64B35"], density="dense")
    asyncio.run(scene_mod.generate_scene_spec(
        Planner(MockLLMClient()), req, store, get_settings(), "mock", style_ref=rep))
    assert "#3C5488" in captured["prompt"]


def test_orchestrator_describe_reference_returns_report(tmp_path):
    """generate 경로에서 reference_image_path가 있으면 _describe_reference가 RefStyleReport 반환."""
    import asyncio

    from figgen.config import Settings
    from figgen.pipeline.orchestrator import Orchestrator
    from figgen.pipeline.planner import Planner
    from figgen.providers import MockLLMClient
    from figgen.schema.requests import GenerationRequest

    ref = tmp_path / "ref.png"
    ref.write_bytes(_PNG)
    orch = Orchestrator(Settings(_env_file=None), store=None)
    planner = Planner(MockLLMClient())
    req = GenerationRequest(description="x", reference_image_path=str(ref))
    report = asyncio.run(orch._describe_reference(req, planner, lambda *a, **k: None))
    assert report is not None and report.palette_hex  # mock 캔드 팔레트


def test_orchestrator_describe_reference_none_without_image(tmp_path):
    import asyncio

    from figgen.config import Settings
    from figgen.pipeline.orchestrator import Orchestrator
    from figgen.pipeline.planner import Planner
    from figgen.providers import MockLLMClient
    from figgen.schema.requests import GenerationRequest

    orch = Orchestrator(Settings(_env_file=None), store=None)
    req = GenerationRequest(description="x")  # 참조 이미지 없음
    report = asyncio.run(
        orch._describe_reference(req, Planner(MockLLMClient()), lambda *a, **k: None))
    assert report is None


def _await_job(client, jid, timeout=10):
    deadline = time.time() + timeout
    d = {}
    while time.time() < deadline:
        d = client.get(f"/api/jobs/{jid}").json()
        if d["status"] in ("succeeded", "failed", "cancelled"):
            return d
        time.sleep(0.05)
    raise AssertionError("job timeout")


# ── CS-3 버그 수정 + CS-4 소형 UX ─────────────────────────────────────────────
def test_plan_accepts_paper_text(client):
    """Bug A: /plan이 paper_text(논문 method)를 받아 분해해도 정상 PlanTurn 반환."""
    pid = _pid(client)
    long_method = ("We encode the input with a ResNet, aggregate features with a transformer, "
                   "then classify the output. ") * 40  # > 1500자
    turn = _plan(client, pid, [{"role": "user", "content": "이 method를 figure로"}],
                 paper_text=long_method)
    assert turn["ready"] is True and turn["plan"]["description"]


def test_plan_research_flag_ok(client):
    """Bug C: research=true여도(mock은 ctx 빈문자) 정상 동작."""
    pid = _pid(client)
    turn = _plan(client, pid, [{"role": "user", "content": "세포 분열 과정"}], research=True)
    assert turn["ready"] is True


def test_enhance_prompt_endpoint(client):
    """CS-4: AI 프롬프트 강화 엔드포인트."""
    pid = _pid(client)
    r = client.post(f"/api/projects/{pid}/enhance-prompt",
                    json={"prompt": "mitosis", "figure_type": "scientific_illustration",
                          "model_prefs": {"provider": "mock"}})
    assert r.status_code == 200, r.text
    assert r.json()["prompt"]


def test_enhance_prompt_requires_text(client):
    pid = _pid(client)
    r = client.post(f"/api/projects/{pid}/enhance-prompt",
                    json={"prompt": "   ", "model_prefs": {"provider": "mock"}})
    assert r.status_code == 400


def test_job_with_palette_and_aspect_succeeds(client):
    """CS-4: 수동 팔레트 + 종횡비 오버라이드 job이 정상 완료되고 팔레트가 스타일시트에 반영."""
    pid = _pid(client)
    r = client.post(f"/api/projects/{pid}/jobs", json={
        "figure_type": "method_diagram", "prompt": "a then b then c",
        "palette": ["#112233", "#445566", "#778899"], "aspect": "square",
        "model_prefs": {"provider": "mock"}})
    assert r.status_code == 202
    d = _await_job(client, r.json()["job_id"])
    assert d["status"] == "succeeded"
    spec = client.get(f"/api/jobs/{r.json()['job_id']}/spec").json()
    pal = [c.lower() for c in spec["stylesheet"]["palette"][:3]]
    assert pal == ["#112233", "#445566", "#778899"]


def test_graphical_abstract_job_succeeds(client):
    """Bug B: graphical_abstract가 전용 장면 경로로 정상 생성된다."""
    pid = _pid(client)
    r = client.post(f"/api/projects/{pid}/jobs", json={
        "figure_type": "graphical_abstract", "prompt": "antibiotic resistance via CRISPR",
        "model_prefs": {"provider": "mock"}})
    assert r.status_code == 202
    d = _await_job(client, r.json()["job_id"])
    assert d["status"] == "succeeded"
    assert set(d["artifacts"]) >= {"figure.svg", "spec.json"}


def test_graphical_abstract_scene_prompt_exists():
    from figgen.pipeline.planner import _load_prompt

    body = _load_prompt("graphical_abstract_scene").lower()
    assert "problem" in body and "result" in body and "scenebrief" in body


def test_generate_with_style_reference_succeeds(client):
    """스타일 참조 이미지를 첨부한 generate job이 정상 완료돼야 한다(_describe_reference 회귀 가드)."""
    pid = _pid(client)
    up = client.post(f"/api/projects/{pid}/uploads",
                     files={"file": ("ref.png", _PNG, "image/png")}, data={"kind": "reference"})
    fid = up.json()["file_id"]
    r = client.post(f"/api/projects/{pid}/jobs", json={
        "task": "generate", "figure_type": "scientific_illustration",
        "prompt": "immune response scene", "reference_image_ids": [fid],
        "model_prefs": {"provider": "mock"}})
    assert r.status_code == 202
    jid = r.json()["job_id"]
    deadline = time.time() + 10
    while time.time() < deadline:
        d = client.get(f"/api/jobs/{jid}").json()
        if d["status"] in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(0.05)
    assert d["status"] == "succeeded"
    assert set(d["artifacts"]) >= {"figure.svg", "spec.json"}
