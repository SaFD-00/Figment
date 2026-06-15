import * as actions from "../actions.js";
import * as api from "../api.js";
import { store } from "../state.js";

// 좌측 대화 패널 — 계획 확정(/plan) + 생성 후 자연어 편집. 단일 생성 진입.
export function mountChatPanel(el) {
  let lastSeed = null;
  const render = () => {
    const s = store.get();
    const { meta, form, chat, jobStatus } = s;
    const running = jobStatus === "running";
    const editMode = !!s.activeJobId && jobStatus === "succeeded";
    const planning = !editMode;

    el.innerHTML = `
      <div class="chat-head">
        <select id="proj" class="mini" title="프로젝트">
          ${s.projects.map((p) => `<option value="${p.project_id}" ${p.project_id === s.currentProjectId ? "selected" : ""}>${escapeHtml(p.name)} (${p.version_count})</option>`).join("")}
        </select>
        <button class="ghost-mini" id="newfig" title="새 figure 시작">＋ 새 figure</button>
      </div>
      <div class="chat-thread" id="thread">${threadHtml(chat, editMode)}</div>
      <div class="chat-foot">
        ${chat.ready && chat.plan && !running ? planCard(chat.plan) : ""}
        ${planning ? attachChips(form) : ""}
        <div class="composer ${running ? "busy" : ""}">
          <textarea id="msg" rows="2" ${running ? "disabled" : ""}
            placeholder="${editMode ? "수정 지시를 입력하세요 (요소 선택 시 해당 요소만)…" : "만들고 싶은 figure를 설명하세요. 데이터·참조 이미지를 첨부할 수 있어요."}"></textarea>
          <div class="composer-tools">
            ${planning ? `
              <button class="tool-btn" data-attach="data" title="데이터 파일 (CSV/JSON · 차트용)">＋ 데이터</button>
              <button class="tool-btn" data-attach="reference" title="참조 스타일 · 스케치 · 정제할 이미지">＋ 이미지</button>
              <button class="tool-btn" id="enhance" title="AI로 프롬프트 강화">💡 강화</button>
              <select id="opt-style" class="mini" title="저널 스타일">
                ${meta.styles.map((st) => `<option value="${st.id}" ${form.style_preset === st.id ? "selected" : ""}>${st.name}</option>`).join("")}
              </select>
              <select id="opt-aspect" class="mini" title="종횡비">
                ${["wide", "square", "tall"].map((a) => `<option value="${a}" ${form.aspect === a ? "selected" : ""}>${a === "wide" ? "Auto" : a}</option>`).join("")}
              </select>` : ""}
            <select id="opt-provider" class="mini" title="provider">
              <option value="mock" ${form.provider === "mock" ? "selected" : ""}>Mock</option>
              ${["openrouter", "openai", "auto"].map((p) => `<option value="${p}" ${form.provider === p ? "selected" : ""} ${p !== "auto" && !meta.providers.includes(p) ? "disabled" : ""}>${p}${p !== "auto" && !meta.providers.includes(p) ? "(키없음)" : ""}</option>`).join("")}
            </select>
            ${planning ? `<span class="model-chip sm" title="이미지 모델">🍌 SeeDream 4.5</span>
            <label class="mini-toggle" title="생성 전 웹검색 그라운딩"><input type="checkbox" id="opt-research" ${form.research ? "checked" : ""}> 리서치</label>` : ""}
            <button class="send-btn" id="send" ${running || chat.pending ? "disabled" : ""} title="보내기 (Enter)">
              ${chat.pending ? "…" : (editMode ? "수정 ▷" : "▷")}</button>
          </div>
        </div>
      </div>`;
    wire(el);
    // 템플릿 카드에서 시드된 starter 프롬프트를 textarea에 1회 주입
    const seed = store.get().chat.seed;
    const ta = el.querySelector("#msg");
    if (ta && seed && seed !== lastSeed) { ta.value = seed; lastSeed = seed; }
    const th = el.querySelector("#thread");
    if (th) th.scrollTop = th.scrollHeight;
  };

  const send = () => {
    const ta = el.querySelector("#msg");
    const v = (ta?.value || "").trim();
    if (!v) return;
    ta.value = "";
    actions.sendPlanMessage(v);
  };

  const wire = (root) => {
    root.querySelector("#proj") && (root.querySelector("#proj").onchange = (e) => actions.setProject(e.target.value));
    root.querySelector("#newfig").onclick = () => actions.newFigure();
    const ta = root.querySelector("#msg");
    if (ta) ta.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } };
    root.querySelector("#send").onclick = send;
    root.querySelector("#opt-provider") && (root.querySelector("#opt-provider").onchange = (e) => actions.setForm({ provider: e.target.value }));
    root.querySelector("#opt-style") && (root.querySelector("#opt-style").onchange = (e) => actions.setForm({ style_preset: e.target.value }));
    root.querySelector("#opt-aspect") && (root.querySelector("#opt-aspect").onchange = (e) => actions.setForm({ aspect: e.target.value }));
    root.querySelector("#opt-research") && (root.querySelector("#opt-research").onchange = (e) => actions.setForm({ research: e.target.checked }));
    const enh = root.querySelector("#enhance");
    if (enh) enh.onclick = async () => {
      const t = root.querySelector("#msg");
      const cur = (t?.value || "").trim();
      if (!cur) return;
      enh.disabled = true; t.disabled = true;
      t.value = await actions.enhancePrompt(cur);
      enh.disabled = false; t.disabled = false; t.focus();
      lastSeed = t.value;
    };
    root.querySelector("#gen-plan") && (root.querySelector("#gen-plan").onclick = () => actions.submitFromPlan());
    root.querySelectorAll("[data-attach]").forEach((b) => b.onclick = () => pickFile(b.dataset.attach));
    root.querySelectorAll(".attach-chip [data-rm]").forEach((b) =>
      b.onclick = () => removeChip(b.dataset.field, b.dataset.rm));
  };

  let last = null;
  store.subscribe((s) => {
    const key = JSON.stringify([
      s.meta.styles.length, s.projects.map((p) => [p.project_id, p.version_count]), s.currentProjectId,
      s.chat.messages.length, s.chat.ready, s.chat.pending, s.chat.seed, s.jobStatus, s.activeJobId,
      s.form,
    ]);
    if (key !== last) { last = key; render(); }
  });
  render();
}

function threadHtml(chat, editMode) {
  if (!chat.messages.length) {
    return `<div class="chat-hero">
      <h2>무엇을 만들까요?</h2>
      <p>논문 figure를 설명하면, 몇 가지를 확인한 뒤 계획을 정리해 드려요. 확정하면 편집 가능한 벡터(PPTX·SVG)로 생성합니다.</p>
      <ul class="hero-hints">
        <li>“대식세포가 박테리아를 포식하는 면역 반응 4단계”</li>
        <li>“encoder–decoder 학습 파이프라인 다이어그램”</li>
        <li>데이터(CSV)를 첨부해 “이 측정값을 막대그래프로”</li>
      </ul>
    </div>`;
  }
  return chat.messages.map((m) => {
    const cls = m.role === "user" ? "msg user" : "msg asst";
    return `<div class="${cls}"><div class="bubble">${escapeHtml(m.content)}</div></div>`;
  }).join("") + (chat.pending ? '<div class="msg asst"><div class="bubble typing">계획 정리 중…</div></div>' : "");
}

function planCard(plan) {
  const TASK = { generate: "생성", sketch: "스케치→정제", refine: "이미지 정제", vectorize: "벡터화" };
  return `<div class="plan-card">
    <div class="pc-head"><span class="pc-tag">${TASK[plan.task] || plan.task}</span>
      <span class="pc-type">${escapeHtml(plan.figure_type)}</span></div>
    ${plan.summary ? `<pre class="pc-summary">${escapeHtml(plan.summary)}</pre>` : ""}
    <button class="btn" id="gen-plan">✨ 이 계획으로 생성</button>
  </div>`;
}

function attachChips(form) {
  const d = form.data_file_ids || [], r = form.reference_image_ids || [];
  if (!d.length && !r.length) return "";
  return `<div class="attach-chips">
    ${d.map((x) => chip(x, "data_file_ids", "📊")).join("")}
    ${r.map((x) => chip(x, "reference_image_ids", "🖼")).join("")}
  </div>`;
}
function chip(x, field, icon) {
  const id = x.id || x, name = x.name || x;
  return `<span class="attach-chip">${icon} ${escapeHtml(name)}<button data-field="${field}" data-rm="${id}">✕</button></span>`;
}

function pickFile(kind) {
  const inp = document.createElement("input");
  inp.type = "file";
  inp.accept = kind === "data" ? ".csv,.json" : "image/*";
  inp.onchange = () => inp.files[0] && upload(inp.files[0], kind);
  inp.click();
}
async function upload(file, kind) {
  const pid = store.get().currentProjectId;
  try {
    const res = await api.uploadFile(pid, file, kind);
    store.set((s) => {
      const field = kind === "data" ? "data_file_ids" : "reference_image_ids";
      return { form: { ...s.form, [field]: [...s.form[field], { id: res.file_id, name: res.filename }] } };
    });
  } catch (e) { alert("업로드 실패: " + e.message); }
}
function removeChip(field, id) {
  store.set((s) => ({ form: { ...s.form, [field]: s.form[field].filter((x) => (x.id || x) !== id) } }));
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
