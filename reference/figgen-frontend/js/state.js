// ~50줄 반응형 스토어 (프레임워크 대체)
export function createStore(initial) {
  let state = { ...initial };
  const subs = new Set();
  return {
    get: () => state,
    set(patch) {
      state = { ...state, ...(typeof patch === "function" ? patch(state) : patch) };
      subs.forEach((fn) => fn(state));
    },
    subscribe(fn) {
      subs.add(fn);
      return () => subs.delete(fn);
    },
  };
}

export const store = createStore({
  meta: { styles: [], models: [], figureTypes: [], providers: [] },
  view: "home", // home | history | projects
  projects: [],
  currentProjectId: null,
  versions: [],
  activeJobId: null,
  jobStatus: null, // running | succeeded | failed | cancelled
  stageEvents: [],
  previewSvg: "",
  specIndex: new Map(), // elementId -> {label, kind, hasAsset}
  selection: new Set(),
  canvasTool: null, // null | region_redraw | text_edit | white_bg | upscale
  region: null, // [x,y,w,h] 0..1 (region_redraw 마스크)
  // figurelabs 랜딩 IA
  templates: { disciplines: [], templates: [], flowcharts: [] }, // /data/templates.json
  mode: "figures", // figures(과학 일러스트) | flowcharts
  discipline: "medicine", // 활성 분야 칩(figures 모드)
  landing: true, // true=갤러리 랜딩, false=활성 대화/캔버스
  credits: 250, // 코스메틱 mock 크레딧(백엔드 미연결)
  // 대화형 계획 상태 (M6) — 프론트가 히스토리 보유, 매 턴 전체를 /plan 으로 전송
  chat: {
    messages: [], // {role:'user'|'assistant', content, plan?}
    ready: false, // 어시스턴트가 계획 확정 → '생성' 버튼 노출
    plan: null, // 확정된 PlanBrief
    pending: false, // /plan 요청 진행중
  },
  // 첨부/옵션 폼 (figure_type·refine_modes 는 대화 계획에서 옴)
  form: {
    style_preset: "nature_minimal", provider: "mock", research: false,
    data_file_ids: [], reference_image_ids: [],
    aspect: "wide", // wide | square | tall (이미지-우선 종횡비)
    palette: [], // 수동 색 팔레트(hex[], 비면 프리셋)
  },
});
