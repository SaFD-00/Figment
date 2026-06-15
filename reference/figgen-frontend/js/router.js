// 초경량 해시 라우터 — Home/History/Projects (생성·편집은 모두 Home 대화에서)
import { store } from "./state.js";

export const VIEWS = ["home", "history", "projects"];

export function currentView() {
  const h = (location.hash || "#/home").replace(/^#\//, "");
  return VIEWS.includes(h) ? h : "home";
}

export function navigate(view) {
  if (location.hash !== `#/${view}`) location.hash = `#/${view}`;
  else store.set({ view });
}

export function startRouter() {
  const apply = () => store.set({ view: currentView() });
  window.addEventListener("hashchange", apply);
  apply();
}
