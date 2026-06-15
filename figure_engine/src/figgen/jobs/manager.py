"""비동기 job 실행기 — 큐, 동시성 제한(Semaphore), 이벤트 팬아웃(SSE), 취소.

파이프라인 대부분이 LLM/이미지 API 대기(IO bound)라 asyncio로 충분. 차트 코드만 subprocess.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Protocol

from .models import JobRecord, JobRequest, JobStatus, StageEvent
from .store import FileStore


class PipelineRunner(Protocol):
    async def run(self, job: JobRecord, progress_cb) -> dict[str, str]: ...


class JobManager:
    def __init__(self, store: FileStore, runner: PipelineRunner, max_concurrent: int = 2):
        self.store = store
        self.runner = runner
        self.sem = asyncio.Semaphore(max_concurrent)
        self._tasks: dict[str, asyncio.Task] = {}
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._seq: dict[str, int] = defaultdict(int)

    async def submit(self, project_id: str, req: JobRequest) -> JobRecord:
        jid = self.store.new_job_id()
        self.store.create_job_dir(project_id, jid)
        rec = JobRecord(job_id=jid, project_id=project_id, status=JobStatus.QUEUED, request=req,
                        parent_job_id=req.parent_job_id, created_at=time.time())
        self.store.save_job(rec)
        self._tasks[jid] = asyncio.create_task(self._run(rec))
        return rec

    def _next_seq(self, jid: str) -> int:
        self._seq[jid] += 1
        return self._seq[jid]

    def _emit(self, jid: str, ev: StageEvent) -> None:
        if ev.seq <= self._seq[jid]:
            ev.seq = self._next_seq(jid)
        else:
            self._seq[jid] = ev.seq
        ev.job_id = jid
        self.store.append_event(jid, ev)
        for q in list(self._subs.get(jid, [])):
            q.put_nowait(ev)

    async def _run(self, rec: JobRecord) -> None:
        jid = rec.job_id
        async with self.sem:
            rec.status = JobStatus.RUNNING
            self.store.save_job(rec)
            try:
                artifacts = await self.runner.run(rec, lambda ev: self._emit(jid, ev))
                fresh = self.store.load_job(jid) or rec
                fresh.status = JobStatus.SUCCEEDED
                fresh.artifacts = artifacts
                fresh.finished_at = time.time()
                self.store.save_job(fresh)
                self._emit(jid, StageEvent(type="done", message="완료",
                                           payload={"artifacts": artifacts}, ts=time.time()))
            except asyncio.CancelledError:
                fresh = self.store.load_job(jid) or rec
                fresh.status = JobStatus.CANCELLED
                fresh.finished_at = time.time()
                self.store.save_job(fresh)
                self._emit(jid, StageEvent(type="error", message="취소됨", ts=time.time()))
                raise
            except Exception as e:  # noqa: BLE001
                fresh = self.store.load_job(jid) or rec
                fresh.status = JobStatus.FAILED
                fresh.error = f"{type(e).__name__}: {e}"
                fresh.finished_at = time.time()
                self.store.save_job(fresh)
                self._emit(jid, StageEvent(type="error", message=fresh.error, ts=time.time()))
            finally:
                for q in list(self._subs.get(jid, [])):
                    q.put_nowait(None)  # 센티널

    async def subscribe(self, jid: str):
        q: asyncio.Queue = asyncio.Queue()
        self._subs[jid].append(q)
        try:
            while True:
                ev = await q.get()
                if ev is None:
                    break
                yield ev
                if ev.type in ("done", "error"):
                    break
        finally:
            if q in self._subs.get(jid, []):
                self._subs[jid].remove(q)

    async def cancel(self, jid: str) -> bool:
        t = self._tasks.get(jid)
        if t and not t.done():
            t.cancel()
            return True
        return False

    def get(self, jid: str) -> JobRecord | None:
        return self.store.load_job(jid)

    def is_active(self, jid: str) -> bool:
        t = self._tasks.get(jid)
        return bool(t and not t.done())

    async def shutdown(self) -> None:
        for t in list(self._tasks.values()):
            if not t.done():
                t.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
