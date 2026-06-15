import * as actions from "../actions.js";
import { store } from "../state.js";

const TASK_TAG = { generate: "", sketch: "sketch", refine: "refine", vectorize: "vector", edit: "edit" };

// ── 사이드 미니 히스토리 (프로젝트 선택 + 버전 목록) ──
export function mountHistoryMini(el) {
  const render = () => {
    const s = store.get();
    const versions = s.versions || [];
    const byId = new Map(versions.map((v) => [v.job_id, v]));
    el.innerHTML = `
      <div class="section-title">버전</div>
      <div class="proj-bar">
        <select id="proj">
          ${s.projects.map((p) => `<option value="${p.project_id}" ${p.project_id === s.currentProjectId ? "selected" : ""}>${escapeHtml(p.name)} (${p.version_count})</option>`).join("")}
        </select>
        <button class="btn ghost sm" id="newp" style="width:auto" title="새 프로젝트">＋</button>
      </div>
      ${versions.length ? versions.map((v, i) => verRow(v, i, byId, s.activeJobId)).join("")
        : '<div class="edit-hint">아직 버전이 없습니다.</div>'}`;
    el.querySelector("#proj").onchange = (e) => actions.setProject(e.target.value);
    el.querySelector("#newp").onclick = () => { const n = prompt("새 프로젝트 이름", "Untitled"); if (n) actions.createProject(n); };
    el.querySelectorAll(".ver").forEach((r) => r.onclick = () => actions.selectJob(r.dataset.job));
  };
  let last = null;
  store.subscribe((s) => {
    const k = JSON.stringify([s.projects.map((p) => [p.project_id, p.version_count]), s.currentProjectId,
      s.versions.map((v) => [v.job_id, v.status, v.thumb_url]), s.activeJobId]);
    if (k !== last) { last = k; render(); }
  });
  render();
}

function verRow(v, i, byId, activeId) {
  const isChild = v.parent_job_id && byId.has(v.parent_job_id);
  const failed = v.status === "failed" || v.status === "cancelled";
  const label = v.edit_summary ? `↳ ${v.edit_summary}` : (v.prompt || `(${v.task || "생성"})`);
  const date = new Date(v.created_at * 1000).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
  return `<div class="ver ${isChild ? "child" : ""} ${v.job_id === activeId ? "sel" : ""}" data-job="${v.job_id}">
    ${v.thumb_url ? `<img src="${v.thumb_url}" alt="">` : '<div class="ph"></div>'}
    <div class="meta"><div class="t">v${i + 1} · ${escapeHtml(truncate(label, 26))}</div>
      <div class="s ${failed ? "st-failed" : ""}">${failed ? "⚠ " + v.status : date}</div></div></div>`;
}

// ── 풀 History 갤러리 ──
export function mountHistoryView(el) {
  const render = () => {
    const s = store.get();
    if (s.view !== "history") return;
    const versions = s.versions || [];
    el.innerHTML = `
      <div class="view-head"><h1>History</h1><span class="count">${versions.length}개 버전</span></div>
      <div class="gallery">
        ${versions.length ? versions.map((v, i) => card(v, `v${i + 1}`, s.activeJobId)).join("")
          : '<div class="edit-hint">아직 버전이 없습니다. Home에서 생성하세요.</div>'}
      </div>`;
    el.querySelectorAll(".card").forEach((c) => c.onclick = async () => {
      await actions.selectJob(c.dataset.job); actions.setView("home");
    });
  };
  store.subscribe((s) => { if (s.view === "history") render(); });
  render();
}

// ── 풀 Projects 갤러리 ──
export function mountProjectsView(el) {
  const render = () => {
    const s = store.get();
    if (s.view !== "projects") return;
    el.innerHTML = `
      <div class="view-head"><h1>Projects</h1><span class="count">${s.projects.length}개</span>
        <span class="spacer"></span>
        <button class="btn ghost sm" id="newp" style="width:auto">＋ 새 프로젝트</button></div>
      <div class="gallery">
        ${s.projects.map((p) => `
          <div class="card ${p.project_id === s.currentProjectId ? "sel" : ""}" data-proj="${p.project_id}">
            <div class="thumb empty">📁</div>
            <div class="body"><div class="title">${escapeHtml(p.name)}</div>
              <div class="sub">${p.version_count}개 버전</div></div>
          </div>`).join("")}
      </div>`;
    el.querySelector("#newp").onclick = () => { const n = prompt("새 프로젝트 이름", "Untitled"); if (n) actions.createProject(n); };
    el.querySelectorAll(".card").forEach((c) => c.onclick = async () => {
      await actions.setProject(c.dataset.proj); actions.setView("home");
    });
  };
  store.subscribe((s) => { if (s.view === "projects") render(); });
  render();
}

function card(v, vlabel, activeId) {
  const failed = v.status === "failed" || v.status === "cancelled";
  const label = v.edit_summary || v.prompt || "(생성)";
  const tag = TASK_TAG[v.task] || "";
  const date = new Date(v.created_at * 1000).toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  return `<div class="card ${v.job_id === activeId ? "sel" : ""}" data-job="${v.job_id}">
    <div class="thumb ${v.thumb_url ? "" : "empty"}">${v.thumb_url ? `<img src="${v.thumb_url}" alt="">` : (failed ? "⚠" : "…")}</div>
    <div class="body">
      <div class="title">${vlabel} · ${escapeHtml(truncate(label, 28))}</div>
      <div class="sub">${tag ? `<span class="tag ${failed ? "fail" : v.task === "edit" ? "edit" : ""}">${tag}</span>` : ""}
        <span>${failed ? "⚠ " + v.status : date}</span></div>
    </div></div>`;
}

function truncate(s, n) { return s.length > n ? s.slice(0, n) + "…" : s; }
function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
