import * as actions from "./actions.js";
import { mountCanvasToolbar } from "./components/canvasToolbar.js";
import { mountChatPanel } from "./components/chatPanel.js";
import { mountDownloads } from "./components/downloads.js";
import { mountHistoryView, mountProjectsView } from "./components/history.js";
import { mountLanding } from "./components/landing.js";
import { mountPreview } from "./components/preview.js";
import { mountProgress } from "./components/progress.js";
import { startRouter } from "./router.js";
import { store } from "./state.js";

function mountNav() {
  const links = [...document.querySelectorAll("#nav-links a, #rail .rail-btn[data-view]")];
  links.forEach((a) => a.onclick = (e) => { e.preventDefault(); actions.setView(a.dataset.view); });
  const railNew = document.querySelector('#rail [data-rail="new"]');
  if (railNew) railNew.onclick = () => { actions.newFigure(); actions.setView("home"); };
  store.subscribe((s) => links.forEach((a) => a.classList.toggle("active", a.dataset.view === s.view)));
}

function mountBadge() {
  const el = document.getElementById("provider-badge");
  const creditN = document.getElementById("credit-n");
  store.subscribe((s) => {
    const provs = s.meta.providers || [];
    el.textContent = provs.length ? `provider: ${provs.join(", ")}` : "provider: mock";
    if (creditN) creditN.textContent = s.credits;
  });
}

// figurelabs: 홈에서 랜딩(갤러리) ↔ 워크스페이스(2-pane) 전환
function mountHomeToggle() {
  const landing = document.getElementById("landing");
  const workspace = document.getElementById("workspace");
  store.subscribe((s) => {
    const showLanding = s.landing && !s.activeJobId && s.jobStatus !== "running";
    landing.classList.toggle("hidden", !showLanding);
    workspace.classList.toggle("hidden", showLanding);
  });
}

function mountViews() {
  const views = {
    home: document.getElementById("view-home"),
    history: document.getElementById("view-history"),
    projects: document.getElementById("view-projects"),
  };
  store.subscribe((s) => {
    for (const [name, el] of Object.entries(views)) el.classList.toggle("hidden", name !== s.view);
  });
}

async function main() {
  startRouter();
  mountNav();
  mountBadge();
  mountViews();
  mountHomeToggle();

  // Home — figurelabs 랜딩(갤러리)
  mountLanding(document.getElementById("landing"));

  // Home 작업공간 — 좌: 대화, 우: 캔버스
  mountChatPanel(document.getElementById("composer"));
  mountCanvasToolbar(document.getElementById("canvas-toolbar"));
  mountProgress(document.getElementById("progress"));
  mountPreview(document.getElementById("preview"), {
    emptyHtml: `<div class="preview-empty"><div class="empty-hero">
      <h2>아이디어를 출판 가능한 과학 figure로</h2>
      <p>왼쪽 대화에서 figure를 설명하고 계획을 확정하면, 결과가 여기 편집 가능한 벡터(PPTX·SVG)로 나타납니다.</p>
      </div></div>`,
  });
  mountDownloads(document.getElementById("downloads"));

  // 풀 뷰
  mountHistoryView(document.getElementById("view-history"));
  mountProjectsView(document.getElementById("view-projects"));

  await actions.init();
}

main().catch((e) => {
  console.error(e);
  document.getElementById("preview").innerHTML =
    `<div class="preview-empty">초기화 오류: ${e.message}</div>`;
});
