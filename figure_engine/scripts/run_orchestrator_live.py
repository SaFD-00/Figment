#!/usr/bin/env python
"""전체 Orchestrator 라이브 구동 — PLANNING→…→CRITIC→FINALIZING (웹앱과 동일 경로).

웹 서버 없이 JobRecord를 손수 만들어 Orchestrator.run을 직접 호출한다. VLM critic(이미지
입력·best-snapshot)을 라이브로 검증하고, critic이 레이아웃 경고를 보정하는지 관찰한다.

    python scripts/run_orchestrator_live.py [--type method_diagram] [--rounds 2] [--provider openai]
"""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from dotenv import load_dotenv

from figgen.config import get_settings
from figgen.jobs.models import JobRecord, JobRequest, ModelPrefs
from figgen.jobs.store import FileStore
from figgen.pipeline.orchestrator import Orchestrator

load_dotenv()

PROMPT = (
    "A two-stage retrieval-augmented generation pipeline: a query encoder embeds the user "
    "question, a dense retriever fetches top-k passages from a vector index, a cross-attention "
    "reranker scores them, and a decoder LLM fuses the reranked context to produce the answer; "
    "include a feedback arrow from answer evaluation back to the retriever."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", default="method_diagram")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--provider", default="openai")
    ap.add_argument("--root", default="/tmp/figgen_orch_root")
    args = ap.parse_args()

    settings = get_settings()
    store = FileStore(Path(args.root))
    proj = store.create_project("live-verify")
    jid = store.new_job_id()
    store.create_job_dir(proj.project_id, jid)

    req = JobRequest(
        figure_type=args.type,  # type: ignore[arg-type]
        prompt=PROMPT,
        style_preset="nature_minimal",
        model_prefs=ModelPrefs(provider=args.provider, max_critic_rounds=args.rounds),
    )
    job = JobRecord(job_id=jid, project_id=proj.project_id, request=req, created_at=time.time())
    store.save_job(job)

    scores: list[str] = []

    def cb(ev) -> None:
        tag = f"[{ev.type}]"
        st = f" {ev.stage}" if ev.stage else ""
        stt = f"/{ev.status}" if ev.status else ""
        msg = f" {ev.message}" if ev.message else ""
        print(f"{tag}{st}{stt}{msg}")
        if "점수" in ev.message:
            scores.append(ev.message)

    print(f"=== Orchestrator 라이브: type={args.type} provider={args.provider} rounds={args.rounds} ===")
    t0 = time.time()
    artifacts = asyncio.run(Orchestrator(settings, store, critic_enabled=True).run(job, cb))
    dt = time.time() - t0

    job_dir = store.job_dir(proj.project_id, jid)
    print(f"\n=== 완료 ({dt:.1f}s) — {job_dir} ===")
    for k, v in artifacts.items():
        print(f"  {k}: {v}")
    print(f"  JOB_DIR={job_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
