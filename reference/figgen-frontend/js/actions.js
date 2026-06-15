// 잡 라이프사이클 + 데이터 로딩 조정 (store를 갱신하면 컴포넌트가 반응)
import * as api from "./api.js";
import { loadTemplates, templateById } from "./data/templates.js";
import { navigate } from "./router.js";
import { store } from "./state.js";

export async function init() {
  try {
    const meta = await api.getMeta();
    const providers = [...new Set(meta.models.filter((m) => !m.disabled).map((m) => m.id.split(":")[0]))];
    store.set({ meta: { ...meta, providers } });
  } catch (e) { console.warn("meta 로드 실패", e); }
  try {
    const templates = await loadTemplates();
    const first = templates.disciplines[0]?.id || "medicine";
    store.set({ templates, discipline: store.get().discipline || first });
  } catch (e) { console.warn("templates 로드 실패", e); }
  await loadProjects();
}

// ── figurelabs 랜딩 IA ──────────────────────────────────────────────────────
export function setMode(mode) {
  const t = store.get().templates;
  const first = t.disciplines[0]?.id || "medicine";
  store.set({ mode, discipline: first });
}
export function setDiscipline(id) { store.set({ discipline: id }); }
export function startBlank() { store.set({ landing: false }); }

// 템플릿 카드 클릭 → 컴포저에 starter 프롬프트 시드(자동 전송 X) + 랜딩 종료
export function pickTemplate(id) {
  const t = templateById(id);
  if (!t) return;
  store.set((s) => ({
    landing: false,
    form: { ...s.form, aspect: t.aspect || "wide" },
    chat: { ...s.chat, seed: t.prompt, figure_type: t.figure_type || null },
  }));
}

export async function enhancePrompt(text) {
  const s = store.get();
  if (!s.currentProjectId || !text.trim()) return text;
  try {
    const r = await api.enhancePrompt(s.currentProjectId, {
      prompt: text, figure_type: s.chat.figure_type || null, model_prefs: _modelPrefs(),
    });
    return r.prompt || text;
  } catch (e) { console.warn("enhance 실패", e); return text; }
}

export async function loadProjects() {
  let projects = await api.listProjects();
  if (!projects.length) {
    await api.createProject("My Figures");
    projects = await api.listProjects();
  }
  const cur = store.get().currentProjectId || projects[0].project_id;
  store.set({ projects, currentProjectId: cur });
  await reloadVersions();
}

export async function reloadVersions() {
  const pid = store.get().currentProjectId;
  if (!pid) return;
  const versions = await api.getVersions(pid);
  store.set({ versions });
}

export async function setProject(pid) {
  store.set({ currentProjectId: pid, activeJobId: null, previewSvg: "", jobStatus: null });
  await reloadVersions();
}

export async function createProject(name) {
  const p = await api.createProject(name || "Untitled");
  store.set({ currentProjectId: p.project_id });
  await loadProjects();
}

export function setView(view) { navigate(view); }
export function setForm(patch) { store.set((s) => ({ form: { ...s.form, ...patch } })); }
export function setAspect(aspect) { setForm({ aspect }); }
export function setPalette(palette) { setForm({ palette }); }
export function setCanvasTool(tool) { store.set((s) => ({ canvasTool: s.canvasTool === tool ? null : tool, region: null })); }
export function setRegion(region) { store.set({ region }); }

function _modelPrefs() { return { provider: store.get().form.provider }; }
const _ids = (arr) => (arr || []).map((x) => x.id || x);

// 새 figure — 대화/캔버스/첨부 초기화 (figurelabs 갤러리 랜딩으로 복귀)
export function newFigure() {
  store.set((s) => ({
    chat: { messages: [], ready: false, plan: null, pending: false },
    activeJobId: null, previewSvg: "", jobStatus: null, stageEvents: [],
    selection: new Set(), specIndex: new Map(), canvasTool: null, region: null,
    landing: true,
    form: { ...s.form, data_file_ids: [], reference_image_ids: [], palette: [] },
  }));
}

// 대화 한 턴 — 생성 전이면 /plan(계획), 생성 후면 자연어 편집 지시.
export async function sendPlanMessage(text) {
  const s = store.get();
  if (!s.currentProjectId || !text.trim() || s.chat.pending) return;
  if (s.activeJobId && s.jobStatus === "succeeded") return _chatEdit(text);

  const messages = [...s.chat.messages, { role: "user", content: text }];
  store.set({ landing: false, chat: { ...s.chat, messages, ready: false, plan: null, pending: true } });
  try {
    const turn = await api.planChat(s.currentProjectId, {
      messages: messages.map((m) => ({ role: m.role, content: m.content })),
      data_file_ids: _ids(s.form.data_file_ids),
      reference_image_ids: _ids(s.form.reference_image_ids),
      style_preset: s.form.style_preset, research: s.form.research,
      model_prefs: _modelPrefs(),
    });
    const plan = turn.ready ? turn.plan : null;
    store.set((st) => ({
      chat: { messages: [...st.chat.messages, { role: "assistant", content: turn.reply, plan }],
        ready: !!turn.ready, plan, pending: false },
    }));
  } catch (e) {
    store.set((st) => ({
      chat: { ...st.chat, pending: false,
        messages: [...st.chat.messages, { role: "assistant", content: "⚠ 오류: " + e.message }] },
    }));
  }
}

// 확정된 계획으로 실제 생성 (기존 /jobs 재사용)
export async function submitFromPlan() {
  const s = store.get();
  const p = s.chat.plan;
  if (!s.currentProjectId || !p) return;
  store.set((st) => ({ chat: { ...st.chat, ready: false } }));
  await _submit({
    task: p.task || "generate", figure_type: p.figure_type, prompt: p.description,
    style_preset: p.style_preset || s.form.style_preset, research: s.form.research,
    palette: s.form.palette || [], aspect: s.form.aspect || null,
    model_prefs: _modelPrefs(),
    data_file_ids: _ids(s.form.data_file_ids), reference_image_ids: _ids(s.form.reference_image_ids),
    refine_modes: p.refine_modes || [],
  });
}

// 생성 후 대화 편집 — 요소 선택 시 해당 요소만, 아니면 전체 수정
async function _chatEdit(instruction) {
  const s = store.get();
  const mode = s.selection.size ? "element" : "global";
  store.set((st) => ({ chat: { ...st.chat,
    messages: [...st.chat.messages, { role: "user", content: instruction }] } }));
  await submitEdit(instruction, mode);
}

// 구조적 부분 재생성(전체/요소) — 자연어 지시
export async function submitEdit(instruction, mode) {
  const { currentProjectId, activeJobId, selection, form } = store.get();
  if (!activeJobId || !instruction.trim()) return;
  await _submit({
    task: "edit", style_preset: form.style_preset, model_prefs: _modelPrefs(),
    parent_job_id: activeJobId,
    edit: { mode, instruction, target_element_ids: [...selection] },
  });
}

// 인-캔버스 도구 (Region Redraw / Text Edit / White BG / Upscale)
export async function submitCanvasOp(kind, { text, instruction, region } = {}) {
  const { activeJobId, selection } = store.get();
  const targetId = [...selection][0];
  if (!activeJobId || !targetId) { alert("먼저 캔버스에서 요소를 선택하세요."); return; }
  await _submit({
    task: "edit", parent_job_id: activeJobId, model_prefs: _modelPrefs(),
    canvas_op: { kind, target_element_id: targetId, text, instruction, region },
  });
  store.set({ canvasTool: null, region: null });
}

async function _submit(req) {
  const pid = store.get().currentProjectId;
  store.set({ jobStatus: "running", stageEvents: [], selection: new Set() });
  const { job_id } = await api.submitJob(pid, req);
  store.set({ activeJobId: job_id });
  api.watchJob(job_id, {
    stage: (ev) => pushEvent(ev),
    log: (ev) => pushEvent(ev),
    preview: (ev) => pushEvent(ev),
    done: () => onJobDone(job_id),
    error: (ev) => { pushEvent({ type: "error", message: ev.message || "실패" });
      store.set({ jobStatus: "failed" }); reloadVersions(); },
  });
}

function pushEvent(ev) { store.set((s) => ({ stageEvents: [...s.stageEvents, ev] })); }

export async function onJobDone(jobId) {
  await loadJob(jobId);
  store.set((s) => ({
    jobStatus: "succeeded",
    chat: { ...s.chat, ready: false, plan: null, messages: [...s.chat.messages,
      { role: "assistant", content: "✓ figure가 준비됐어요. 캔버스에서 확인하고, 요소를 클릭해 수정 지시를 보내거나 상단 도구로 편집하세요." }] },
  }));
  await reloadVersions();
}

export async function loadJob(jobId) {
  const [spec, svg] = await Promise.all([
    api.getSpec(jobId).catch(() => null),
    api.getPreviewSvg(jobId).catch(() => ""),
  ]);
  const idx = new Map();
  if (spec) buildIndex(spec.root, idx);
  store.set({ activeJobId: jobId, previewSvg: svg, specIndex: idx, selection: new Set() });
}

export async function selectJob(jobId) {
  const rec = await api.getJob(jobId).catch(() => null);
  store.set({ jobStatus: rec ? rec.status : null });
  await loadJob(jobId);
}

function buildIndex(node, idx) {
  if (!node) return;
  if (node.id && node.type) {
    idx.set(node.id, {
      label: node.label || node.text || node.alt || node.id,
      kind: node.type, hasAsset: !!node.asset_id,
    });
  }
  (node.children || []).forEach((c) => buildIndex(c, idx));
  (node.items || []).forEach((it) => buildIndex(it.node, idx));
}

export function toggleSelect(id, multi) {
  store.set((s) => {
    const sel = new Set(multi ? s.selection : []);
    if (sel.has(id)) sel.delete(id); else sel.add(id);
    return { selection: sel };
  });
}

export function clearSelection() { store.set({ selection: new Set() }); }
