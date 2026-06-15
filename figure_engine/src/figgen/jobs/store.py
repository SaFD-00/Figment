"""outputs/ 파일 기반 영속화 계층 (DB 대체).

레이아웃: outputs/projects/{pid}/project.json + inputs/{file_id}_{name}
         + jobs/{jid}/{job.json, spec.json, figure.pptx, figure.svg, preview.svg, preview.png, assets/*}
모든 JSON 쓰기는 tmp + os.replace 원자적 교체(Google Drive 동기화 충돌 완화). 시작 시 스캔으로 인덱스 재구축.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from pydantic import BaseModel

from .models import JobRecord, JobStatus, StageEvent


class ProjectMeta(BaseModel):
    project_id: str
    name: str
    created_at: float = 0.0


class UploadResult(BaseModel):
    file_id: str
    filename: str
    kind: str


class FileStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.projects_root = self.root / "projects"
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self._job_index: dict[str, Path] = {}
        self._input_index: dict[str, Path] = {}
        self.scan_all()

    # ── 스캔/인덱스 ─────────────────────────────────────────────────────────────
    def scan_all(self) -> None:
        self._job_index.clear()
        self._input_index.clear()
        for pdir in self.projects_root.glob("*"):
            if not pdir.is_dir():
                continue
            for jdir in (pdir / "jobs").glob("*"):
                if (jdir / "job.json").exists():
                    self._job_index[jdir.name] = jdir
            for f in (pdir / "inputs").glob("*"):
                fid = f.name.split("_", 1)[0]
                self._input_index[fid] = f

    # ── 프로젝트 ─────────────────────────────────────────────────────────────────
    def create_project(self, name: str) -> ProjectMeta:
        pid = "p_" + uuid.uuid4().hex[:10]
        meta = ProjectMeta(project_id=pid, name=name, created_at=time.time())
        d = self.project_dir(pid)
        (d / "jobs").mkdir(parents=True, exist_ok=True)
        (d / "inputs").mkdir(parents=True, exist_ok=True)
        self.save_project(meta)
        return meta

    def project_dir(self, pid: str) -> Path:
        return self.projects_root / pid

    def save_project(self, meta: ProjectMeta) -> None:
        self.project_dir(meta.project_id).mkdir(parents=True, exist_ok=True)
        _atomic_write(self.project_dir(meta.project_id) / "project.json",
                      meta.model_dump_json(indent=2).encode())

    def load_project(self, pid: str) -> ProjectMeta | None:
        p = self.project_dir(pid) / "project.json"
        if not p.exists():
            return None
        return ProjectMeta.model_validate_json(p.read_text("utf-8"))

    def list_projects(self) -> list[ProjectMeta]:
        out = []
        for pdir in self.projects_root.glob("*"):
            mp = pdir / "project.json"
            if mp.exists():
                out.append(ProjectMeta.model_validate_json(mp.read_text("utf-8")))
        return sorted(out, key=lambda m: m.created_at, reverse=True)

    def rename_project(self, pid: str, name: str) -> ProjectMeta | None:
        meta = self.load_project(pid)
        if meta is None:
            return None
        meta.name = name
        self.save_project(meta)
        return meta

    def delete_project(self, pid: str) -> bool:
        import shutil

        d = self.project_dir(pid)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            self.scan_all()
            return True
        return False

    # ── 업로드 ───────────────────────────────────────────────────────────────────
    def save_upload(self, pid: str, filename: str, data: bytes, kind: str) -> UploadResult:
        fid = "f_" + uuid.uuid4().hex[:10]
        safe = Path(filename).name
        dest = self.project_dir(pid) / "inputs" / f"{fid}_{safe}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(dest, data)
        self._input_index[fid] = dest
        return UploadResult(file_id=fid, filename=safe, kind=kind)

    def resolve_input(self, file_id: str) -> Path | None:
        return self._input_index.get(file_id)

    # ── job ──────────────────────────────────────────────────────────────────────
    def new_job_id(self) -> str:
        return f"j_{time.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"

    def job_dir(self, pid: str, jid: str) -> Path:
        return self.project_dir(pid) / "jobs" / jid

    def create_job_dir(self, pid: str, jid: str) -> Path:
        d = self.job_dir(pid, jid)
        (d / "assets").mkdir(parents=True, exist_ok=True)
        self._job_index[jid] = d
        return d

    def save_job(self, record: JobRecord) -> None:
        d = self._job_index.get(record.job_id) or self.job_dir(record.project_id, record.job_id)
        d.mkdir(parents=True, exist_ok=True)
        _atomic_write(d / "job.json", record.model_dump_json(indent=2).encode())
        self._job_index[record.job_id] = d

    def load_job(self, jid: str) -> JobRecord | None:
        d = self._job_index.get(jid)
        if d is None or not (d / "job.json").exists():
            return None
        return JobRecord.model_validate_json((d / "job.json").read_text("utf-8"))

    def list_jobs(self, pid: str) -> list[JobRecord]:
        jobs = []
        for jdir in (self.project_dir(pid) / "jobs").glob("*"):
            jp = jdir / "job.json"
            if jp.exists():
                jobs.append(JobRecord.model_validate_json(jp.read_text("utf-8")))
        return sorted(jobs, key=lambda j: j.created_at)

    def append_event(self, jid: str, ev: StageEvent) -> None:
        rec = self.load_job(jid)
        if rec is None:
            return
        rec.stages.append(ev)
        self.save_job(rec)

    def load_events(self, jid: str, after_seq: int = 0) -> list[StageEvent]:
        rec = self.load_job(jid)
        if rec is None:
            return []
        return [e for e in rec.stages if e.seq > after_seq]

    def recover_interrupted_jobs(self) -> int:
        n = 0
        for jid in list(self._job_index):
            rec = self.load_job(jid)
            if rec and rec.status in (JobStatus.RUNNING, JobStatus.QUEUED):
                rec.status = JobStatus.FAILED
                rec.error = "server restarted (interrupted)"
                rec.finished_at = time.time()
                self.save_job(rec)
                n += 1
        return n


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)
