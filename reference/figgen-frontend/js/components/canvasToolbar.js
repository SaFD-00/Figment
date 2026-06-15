import * as actions from "../actions.js";
import { store } from "../state.js";

// figurelabs 인-캔버스 도구: Region Redraw / Text Edit / White BG / Upscale
export function mountCanvasToolbar(el) {
  const render = () => {
    const s = store.get();
    const ready = s.activeJobId && s.jobStatus === "succeeded";
    if (!ready) { el.classList.remove("active"); el.innerHTML = ""; return; }
    el.classList.add("active");

    const selId = [...s.selection][0];
    const info = selId ? s.specIndex.get(selId) : null;
    const isImage = !!(info && info.hasAsset);
    const isText = !!(info && (info.kind === "text" || info.kind === "box"));
    const regionOn = s.canvasTool === "region_redraw";

    el.innerHTML = `
      <button class="ctool ${regionOn ? "active" : ""}" data-act="region-toggle" title="캔버스에서 영역 드래그">
        <span class="ic">▢</span> 영역</button>
      <button class="ctool" data-act="region_redraw" ${isImage ? "" : "disabled"}>
        <span class="ic">✦</span> Region Redraw</button>
      <button class="ctool" data-act="text_edit" ${isText ? "" : "disabled"}>
        <span class="ic">T</span> Text Edit</button>
      <button class="ctool" data-act="white_bg" ${isImage ? "" : "disabled"}>
        <span class="ic">◻</span> White BG</button>
      <button class="ctool" data-act="upscale" ${isImage ? "" : "disabled"}>
        <span class="ic">⤢</span> Upscale</button>
      <span class="sel-note">${selId ? `선택: ${escapeHtml(info?.label || selId)}${s.region ? " · 영역 지정됨" : ""}` : "요소를 클릭해 선택"}</span>`;

    el.querySelectorAll(".ctool").forEach((b) => b.onclick = () => act(b.dataset.act));
  };

  const act = (a) => {
    const s = store.get();
    const selId = [...s.selection][0];
    if (a === "region-toggle") { actions.setCanvasTool("region_redraw"); return; }
    if (a === "text_edit") {
      const cur = s.specIndex.get(selId)?.label || "";
      const text = prompt("새 텍스트", cur);
      if (text != null) actions.submitCanvasOp("text_edit", { text });
      return;
    }
    if (a === "region_redraw") {
      const instruction = prompt("이 영역을 어떻게 재생성할까요?", "");
      if (instruction != null) actions.submitCanvasOp("region_redraw", { instruction, region: s.region });
      return;
    }
    if (a === "white_bg") actions.submitCanvasOp("white_bg", {});
    if (a === "upscale") actions.submitCanvasOp("upscale", {});
  };

  let last = null;
  store.subscribe((s) => {
    const key = JSON.stringify([s.activeJobId, s.jobStatus, [...s.selection], s.canvasTool, !!s.region]);
    if (key !== last) { last = key; render(); }
  });
  render();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
