import * as api from "../api.js";
import { store } from "../state.js";

const STEPS = [
  ["planning", "계획"], ["styling", "스타일"], ["assets", "에셋"],
  ["rendering", "렌더"], ["critic", "비평"], ["finalizing", "마무리"],
];

export function mountProgress(el) {
  const render = () => {
    const s = store.get();
    if (!s.jobStatus) { el.classList.remove("active"); el.innerHTML = ""; return; }
    el.classList.add("active");

    const state = {};
    let assetsProg = "";
    for (const ev of s.stageEvents) {
      if (ev.type === "stage" && ev.stage) {
        if (ev.status === "started") state[ev.stage] = state[ev.stage] === "done" ? "done" : "run";
        if (ev.status === "completed") state[ev.stage] = "done";
        if (ev.stage === "assets" && ev.payload && ev.payload.total)
          assetsProg = ` ${ev.payload.done + 1}/${ev.payload.total}`;
      }
    }
    if (s.jobStatus === "failed") {
      const running = STEPS.find(([k]) => state[k] === "run");
      if (running) state[running[0]] = "err";
    }
    const logs = s.stageEvents.filter((e) => e.type === "log" || e.type === "error")
      .slice(-50).map((e) => e.message).filter(Boolean);

    el.innerHTML = `
      <div class="stepper">
        ${STEPS.map(([k, label], i) => `
          <span class="step ${state[k] || ""}">
            <span class="dot">${state[k] === "done" ? "✓" : state[k] === "err" ? "!" : ""}</span>
            ${label}${k === "assets" ? assetsProg : ""}
          </span>${i < STEPS.length - 1 ? '<span class="arr">›</span>' : ""}`).join("")}
        ${s.jobStatus === "running" ? '<button class="btn ghost sm" id="cancel" style="width:auto;margin-left:auto">취소</button>' : ""}
      </div>
      ${logs.length ? `<div class="log">${logs.map((l) => escapeHtml(l)).join("<br>")}</div>` : ""}`;

    const c = el.querySelector("#cancel");
    if (c) c.onclick = () => s.activeJobId && api.cancelJob(s.activeJobId);
    const log = el.querySelector(".log");
    if (log) log.scrollTop = log.scrollHeight;
  };
  store.subscribe(render);
  render();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}
