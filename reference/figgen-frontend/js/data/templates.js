// 분야/템플릿 갤러리 데이터 로더 — frontend/data/templates.json (JS+Python 공용 소스)
const EMPTY = { disciplines: [], templates: [], flowcharts: [] };
let _cache = null;

export async function loadTemplates() {
  if (_cache) return _cache;
  try {
    const r = await fetch("/data/templates.json");
    _cache = r.ok ? await r.json() : EMPTY;
  } catch {
    _cache = EMPTY;
  }
  return _cache;
}

export function templateById(id) {
  const d = _cache || EMPTY;
  return [...d.templates, ...d.flowcharts].find((t) => t.id === id) || null;
}
