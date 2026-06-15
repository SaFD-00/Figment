import { exportUrl, fileUrl } from "../api.js";
import { store } from "../state.js";

export function mountDownloads(el) {
  const render = () => {
    const s = store.get();
    const ready = s.activeJobId && s.jobStatus === "succeeded";
    if (!ready) { el.classList.remove("active"); el.innerHTML = ""; return; }
    el.classList.add("active");
    const jid = s.activeJobId;
    el.innerHTML = `
      <a class="dl" href="${fileUrl(jid, "figure.pptx")}" download>⬇ PPTX</a>
      <a class="dl" href="${fileUrl(jid, "figure.svg")}" download>⬇ SVG</a>
      <div class="dl-menu">
        <button class="dl" id="dl-export">⬇ Export ▾</button>
        <div class="dl-pop hidden" id="dl-pop">
          <a href="${exportUrl(jid, "figure.png", { res: "1k" })}" download>PNG · 1K</a>
          <a href="${exportUrl(jid, "figure.png", { res: "4k" })}" download>PNG · 4K <i class="cost">✦2</i></a>
          <a href="${exportUrl(jid, "figure.png", { res: "8k" })}" download>PNG · 8K <i class="cost">✦4</i></a>
          <a href="${exportUrl(jid, "figure.jpg", { res: "4k" })}" download>JPG · 4K</a>
        </div>
      </div>
      <a class="dl" href="${fileUrl(jid, "spec.json")}" download>spec.json</a>
      <span class="sp">PPTX·SVG는 PowerPoint/Illustrator에서 후편집 가능</span>`;
    const btn = el.querySelector("#dl-export");
    const pop = el.querySelector("#dl-pop");
    btn.onclick = (e) => { e.stopPropagation(); pop.classList.toggle("hidden"); };
    pop.querySelectorAll("a").forEach((a) => a.onclick = () => pop.classList.add("hidden"));
  };
  document.addEventListener("click", () => {
    const pop = el.querySelector("#dl-pop");
    if (pop) pop.classList.add("hidden");
  });
  let last = null;
  store.subscribe((s) => {
    const key = `${s.activeJobId}|${s.jobStatus}`;
    if (key !== last) { last = key; render(); }
  });
  render();
}
