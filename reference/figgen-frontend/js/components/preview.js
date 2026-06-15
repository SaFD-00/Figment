import * as actions from "../actions.js";
import { store } from "../state.js";

// 편집 가능 SVG 캔버스 — data-fg-id 선택/zoom·pan + 더블클릭 Text Edit + region 드래그.
// Home 캔버스와 SVG Editor 뷰가 각각 인스턴스로 마운트한다(class host, id 충돌 회피).
export function mountPreview(el, { emptyHtml } = {}) {
  let lastSvg = null, vb = null, svgEl = null, host = null;

  const render = () => {
    const s = store.get();
    if (!s.previewSvg) {
      if (lastSvg !== "") {
        el.innerHTML = emptyHtml || '<div class="preview-empty">미리보기가 여기에 표시됩니다.</div>';
        lastSvg = ""; svgEl = null;
      }
      return;
    }
    if (s.previewSvg !== lastSvg) { lastSvg = s.previewSvg; inject(s.previewSvg); }
    updateSelection(s.selection);
    host && host.classList.toggle("region-mode", s.canvasTool === "region_redraw");
  };

  const inject = (svgText) => {
    el.innerHTML = `<div class="svg-host"></div>
      <div class="toolbar">
        <button data-z="in">＋</button><button data-z="out">－</button>
        <button data-z="fit">⤢</button><button data-z="reset">100%</button>
      </div>`;
    host = el.querySelector(".svg-host");
    host.innerHTML = sanitize(svgText);
    svgEl = host.querySelector("svg");
    if (!svgEl) return;
    svgEl.removeAttribute("width"); svgEl.removeAttribute("height");
    svgEl.style.width = "100%"; svgEl.style.height = "100%";
    const p = (svgEl.getAttribute("viewBox") || "0 0 180 120").split(/[ ,]+/).map(Number);
    vb = { x: p[0], y: p[1], w: p[2], h: p[3], x0: p[0], y0: p[1], w0: p[2], h0: p[3] };
    const ov = svgNode("g"); ov.setAttribute("id", "fg-sel"); svgEl.appendChild(ov);

    setupZoomPan();
    host.addEventListener("click", (e) => {
      if (store.get().canvasTool === "region_redraw") return;
      const g = e.target.closest("[data-fg-id]");
      if (!g) { actions.clearSelection(); return; }
      actions.toggleSelect(g.getAttribute("data-fg-id"), e.shiftKey);
    });
    host.addEventListener("dblclick", (e) => {
      const g = e.target.closest("[data-fg-id]");
      if (!g) return;
      const id = g.getAttribute("data-fg-id");
      const info = store.get().specIndex.get(id);
      if (info && (info.kind === "text" || info.kind === "box")) {
        const text = prompt("새 텍스트", info.label || "");
        if (text != null) { actions.toggleSelect(id, false); actions.submitCanvasOp("text_edit", { text }); }
      }
    });
    host.addEventListener("mouseover", (e) => {
      const g = e.target.closest("[data-fg-id]"); if (g) g.classList.add("fg-hover");
    });
  };

  const setVb = () => svgEl && svgEl.setAttribute("viewBox", `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
  const ptToVb = (clientX, clientY) => {
    const r = svgEl.getBoundingClientRect();
    return { x: vb.x + ((clientX - r.left) / r.width) * vb.w, y: vb.y + ((clientY - r.top) / r.height) * vb.h };
  };

  const setupZoomPan = () => {
    host.onwheel = (e) => {
      e.preventDefault();
      const m = ptToVb(e.clientX, e.clientY);
      const f = e.deltaY < 0 ? 0.88 : 1.14;
      const nw = Math.min(vb.w0 * 6, Math.max(vb.w0 * 0.15, vb.w * f));
      const nh = nw * (vb.h / vb.w);
      vb.x = m.x - (m.x - vb.x) * (nw / vb.w); vb.y = m.y - (m.y - vb.y) * (nh / vb.h);
      vb.w = nw; vb.h = nh; setVb();
    };
    let drag = null, region = null, regionRect = null;
    host.onpointerdown = (e) => {
      if (store.get().canvasTool === "region_redraw") {
        const m = ptToVb(e.clientX, e.clientY);
        region = { x0: m.x, y0: m.y };
        regionRect = svgNode("rect"); regionRect.setAttribute("id", "region-rect"); svgEl.appendChild(regionRect);
      } else { drag = { x: e.clientX, y: e.clientY }; }
      host.setPointerCapture(e.pointerId);
    };
    host.onpointermove = (e) => {
      if (region && regionRect) {
        const m = ptToVb(e.clientX, e.clientY);
        const x = Math.min(region.x0, m.x), y = Math.min(region.y0, m.y);
        const w = Math.abs(m.x - region.x0), h = Math.abs(m.y - region.y0);
        regionRect.setAttribute("x", x); regionRect.setAttribute("y", y);
        regionRect.setAttribute("width", w); regionRect.setAttribute("height", h);
        region.cur = { x, y, w, h };
      } else if (drag) {
        const r = svgEl.getBoundingClientRect();
        vb.x -= ((e.clientX - drag.x) / r.width) * vb.w; vb.y -= ((e.clientY - drag.y) / r.height) * vb.h;
        drag = { x: e.clientX, y: e.clientY }; setVb();
      }
    };
    host.onpointerup = () => {
      if (region && region.cur) {
        // viewBox 좌표 → 캔버스(=풀블리드 이미지) 0..1 분수
        const c = region.cur;
        actions.setRegion([(c.x - vb.x0) / vb.w0, (c.y - vb.y0) / vb.h0, c.w / vb.w0, c.h / vb.h0]);
      }
      region = null; regionRect = null; drag = null;
    };
    el.querySelectorAll(".toolbar button").forEach((b) => b.onclick = () => zoomCmd(b.dataset.z));
  };

  const zoomCmd = (cmd) => {
    if (!vb) return;
    if (cmd === "in") { vb.w *= 0.83; vb.h *= 0.83; }
    else if (cmd === "out") { vb.w *= 1.2; vb.h *= 1.2; }
    else Object.assign(vb, { x: vb.x0, y: vb.y0, w: vb.w0, h: vb.h0 });
    setVb();
  };

  const updateSelection = (selection) => {
    if (!svgEl) return;
    const ov = svgEl.querySelector("#fg-sel"); if (!ov) return;
    ov.innerHTML = "";
    selection.forEach((id) => {
      const g = svgEl.querySelector(`[data-fg-id="${CSS.escape(id)}"]`); if (!g) return;
      let bb; try { bb = g.getBBox(); } catch { return; }
      const r = svgNode("rect");
      r.setAttribute("x", bb.x - 0.8); r.setAttribute("y", bb.y - 0.8);
      r.setAttribute("width", bb.width + 1.6); r.setAttribute("height", bb.height + 1.6);
      r.setAttribute("fill", "none"); r.setAttribute("stroke", "#d97757");
      r.setAttribute("stroke-width", "0.6"); r.setAttribute("stroke-dasharray", "1.5 1"); r.setAttribute("rx", "1");
      ov.appendChild(r);
    });
  };

  store.subscribe(render);
  render();
}

function svgNode(tag) { return document.createElementNS("http://www.w3.org/2000/svg", tag); }
function sanitize(svg) {
  return svg.replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/\son\w+="[^"]*"/gi, "")
    .replace(/(href|xlink:href)\s*=\s*"javascript:[^"]*"/gi, "");
}
