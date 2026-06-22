// figurelabs 풀폭 랜딩 — 히어로 + 2모드 토글 + 프롬프트 박스 + 분야 갤러리 + Recent.
import * as actions from "../actions.js";
import * as api from "../api.js";
import { store } from "../state.js";

const MODEL_LABEL = "Gemini 3.1 Flash Image"; // 이미지 모델(컴포저 라벨, figurelabs 'Nano Banana Pro' 자리)

export function mountLanding(el) {
  let palOpen = false;

  const render = () => {
    const s = store.get();
    const { templates, mode, discipline, form, meta, projects, currentProjectId, credits } = s;
    const figures = mode === "figures";
    const cards = figures
      ? templates.templates.filter((t) => t.discipline === discipline)
      : templates.flowcharts;
    const proj = projects.find((p) => p.project_id === currentProjectId);

    el.innerHTML = `
      <div class="landing-inner">
        <div class="land-hero">
          <h1>Scientific figures. <span>made effortless.</span></h1>
          <p>Turn text, sketches, and reference images into editable, publication-ready figures.</p>
        </div>

        <div class="mode-seg">
          <button class="seg ${figures ? "active" : ""}" data-mode="figures">✦ Scientific Figures</button>
          <button class="seg ${!figures ? "active" : ""}" data-mode="flowcharts">≈ Flowcharts <em>Beta</em></button>
        </div>

        <div class="prompt-card">
          <div class="pc-modes">
            <button class="pc-mode" data-input="enhance">Enhance Figure</button>
            <button class="pc-mode" data-input="sketch">Sketch to Figure</button>
            <button class="pc-mode" data-input="reference">Add Ref Figure</button>
          </div>
          <textarea id="land-msg" rows="2" placeholder="${figures
            ? "Describe the scientific figure you want to create…"
            : "Describe the flowchart or diagram you want to create…"}"></textarea>
          <div class="pc-tools">
            <div class="pc-left">
              <button class="ic-btn" data-attach="reference" title="파일 업로드">📎</button>
              <button class="ic-btn" id="land-enhance" title="AI로 프롬프트 강화">💡</button>
              <button class="ic-btn ${form.palette.length ? "on" : ""}" id="land-pal" title="색 팔레트">🎨</button>
              ${palettePop(form.palette, palOpen)}
            </div>
            <div class="pc-right">
              <span class="model-chip" title="이미지 모델">🍌 ${MODEL_LABEL}</span>
              <select id="land-style" class="chip-sel" title="스타일">
                ${(meta.styles || []).map((st) => `<option value="${st.id}" ${form.style_preset === st.id ? "selected" : ""}>${esc(st.name)}</option>`).join("")}
              </select>
              <select id="land-aspect" class="chip-sel" title="종횡비">
                ${["wide", "square", "tall"].map((a) => `<option value="${a}" ${form.aspect === a ? "selected" : ""}>${a === "wide" ? "Auto" : a}</option>`).join("")}
              </select>
              <button class="send-round" id="land-send" title="생성 시작">↑</button>
            </div>
          </div>
        </div>

        ${figures ? disciplineChips(templates.disciplines, discipline) : ""}
        <div class="tpl-grid">
          ${cards.map((t) => cardHtml(t)).join("")}
        </div>

        <div class="recent">
          <h2>Recent Projects</h2>
          <div class="recent-card">
            <div class="recent-empty">
              <div class="re-ico">🗂</div>
              <div>${proj ? esc(proj.name) : "My Figures"} · ${proj ? proj.version_count : 0} figures<br>
                <span>위에서 생성하면 결과가 여기 모입니다.</span></div>
            </div>
          </div>
        </div>
      </div>`;
    wire(el);
  };

  const send = () => {
    const ta = el.querySelector("#land-msg");
    const v = (ta?.value || "").trim();
    if (!v) return;
    actions.sendPlanMessage(v);
  };

  const wire = (root) => {
    root.querySelectorAll("[data-mode]").forEach((b) => b.onclick = () => actions.setMode(b.dataset.mode));
    root.querySelectorAll("[data-disc]").forEach((b) => b.onclick = () => actions.setDiscipline(b.dataset.disc));
    root.querySelectorAll(".tpl-card").forEach((c) => c.onclick = () => actions.pickTemplate(c.dataset.tpl));
    root.querySelector("#land-send").onclick = send;
    const ta = root.querySelector("#land-msg");
    if (ta) ta.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } };
    root.querySelector("#land-style").onchange = (e) => actions.setForm({ style_preset: e.target.value });
    root.querySelector("#land-aspect").onchange = (e) => actions.setForm({ aspect: e.target.value });
    root.querySelectorAll("[data-attach]").forEach((b) => b.onclick = () => pickRef());
    root.querySelector("#land-enhance").onclick = async () => {
      const cur = ta.value.trim();
      if (!cur) return;
      ta.disabled = true;
      ta.value = await actions.enhancePrompt(cur);
      ta.disabled = false; ta.focus();
    };
    root.querySelector("#land-pal").onclick = () => { palOpen = !palOpen; render(); };
    wirePalette(root, () => render());
  };

  let last = null;
  store.subscribe((s) => {
    const key = JSON.stringify([
      s.mode, s.discipline, s.templates.templates.length, s.templates.flowcharts.length,
      s.form.style_preset, s.form.aspect, s.form.palette,
      s.projects.map((p) => [p.project_id, p.version_count]), s.currentProjectId,
      (s.meta.styles || []).length, s.credits,
    ]);
    if (key !== last) { last = key; render(); }
  });
  render();
}

function disciplineChips(disciplines, active) {
  return `<div class="disc-chips">
    ${disciplines.map((d) => `<button class="disc-chip ${d.id === active ? "active" : ""}" data-disc="${d.id}">
      <span class="di">${d.icon}</span> ${esc(d.label)}</button>`).join("")}
  </div>`;
}

function cardHtml(t) {
  const thumb = t.thumb || `/img/templates/${t.id}.png`;
  return `<div class="tpl-card" data-tpl="${t.id}" title="${esc(t.prompt)}">
    <div class="tpl-thumb"><img src="${thumb}" alt="${esc(t.title)}" loading="lazy"
      onerror="this.closest('.tpl-thumb').classList.add('ph');this.remove();"
      ><span class="ph-label">${esc(t.title)}</span></div>
    <div class="tpl-name">${esc(t.title)}</div>
  </div>`;
}

function palettePop(palette, open) {
  if (!open) return "";
  const swatches = (palette.length ? palette : ["#3b82f6"]).slice(0, 6);
  return `<div class="palette-pop">
    <div class="pp-row">
      ${swatches.map((c, i) => `<input type="color" data-pi="${i}" value="${c}">`).join("")}
      ${swatches.length < 6 ? '<button class="pp-add" title="색 추가">＋</button>' : ""}
    </div>
    <button class="pp-clear" ${palette.length ? "" : "disabled"}>지우기(프리셋 사용)</button>
  </div>`;
}

function wirePalette(root, rerender) {
  const cur = () => store.get().form.palette.slice();
  root.querySelectorAll("[data-pi]").forEach((inp) => {
    inp.oninput = (e) => {
      const p = store.get().form.palette.length ? cur() : ["#3b82f6"];
      p[+inp.dataset.pi] = e.target.value;
      actions.setPalette(p.slice(0, 6));
    };
  });
  const add = root.querySelector(".pp-add");
  if (add) add.onclick = () => { const p = cur(); p.push("#22c55e"); actions.setPalette(p.slice(0, 6)); rerender(); };
  const clr = root.querySelector(".pp-clear");
  if (clr) clr.onclick = () => { actions.setPalette([]); rerender(); };
}

function pickRef() {
  const inp = document.createElement("input");
  inp.type = "file"; inp.accept = "image/*";
  inp.onchange = async () => {
    const f = inp.files[0];
    if (!f) return;
    const pid = store.get().currentProjectId;
    try {
      const res = await api.uploadFile(pid, f, "reference");
      store.set((s) => ({ form: { ...s.form, reference_image_ids: [...s.form.reference_image_ids, { id: res.file_id, name: res.filename }] } }));
      alert("이미지 첨부됨 — 프롬프트로 용도(스케치/참조/정제)를 알려주세요.");
    } catch (e) { alert("업로드 실패: " + e.message); }
  };
  inp.click();
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
