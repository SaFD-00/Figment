// 백엔드 API 클라이언트 (fetch + EventSource)
async function j(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text().catch(() => "")}`);
  return r.status === 204 ? null : r.json();
}

export const getMeta = async () => ({
  styles: await j("/api/meta/styles"),
  models: await j("/api/meta/models"),
  figureTypes: await j("/api/meta/figure-types"),
});

export const listProjects = () => j("/api/projects");
export const createProject = (name) =>
  j("/api/projects", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }) });
export const getProject = (id) => j(`/api/projects/${id}`);
export const getVersions = (id) => j(`/api/projects/${id}/versions`);

export async function uploadFile(projectId, file, kind) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("kind", kind);
  const r = await fetch(`/api/projects/${projectId}/uploads`, { method: "POST", body: fd });
  if (!r.ok) throw new Error("업로드 실패");
  return r.json();
}

export const planChat = (projectId, body) =>
  j(`/api/projects/${projectId}/plan`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const enhancePrompt = (projectId, body) =>
  j(`/api/projects/${projectId}/enhance-prompt`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const submitJob = (projectId, req) =>
  j(`/api/projects/${projectId}/jobs`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) });
export const getJob = (jobId) => j(`/api/jobs/${jobId}`);
export const cancelJob = (jobId) => j(`/api/jobs/${jobId}/cancel`, { method: "POST" });
export const getSpec = (jobId) => j(`/api/jobs/${jobId}/spec`);
export const getPreviewSvg = async (jobId) => (await fetch(`/api/jobs/${jobId}/preview.svg`)).text();
export const fileUrl = (jobId, name) => `/api/jobs/${jobId}/files/${name}`;
export const exportUrl = (jobId, name, { res, format } = {}) => {
  const q = new URLSearchParams();
  if (res) q.set("res", res);
  if (format) q.set("format", format);
  const qs = q.toString();
  return `/api/jobs/${jobId}/files/${name}${qs ? `?${qs}` : ""}`;
};

// SSE + 폴링 폴백
export function watchJob(jobId, handlers) {
  let es = null, pollTimer = null, retries = 0, closed = false;
  const stop = () => { closed = true; if (es) es.close(); if (pollTimer) clearInterval(pollTimer); };
  const onMsg = (type) => (e) => {
    let data = {};
    try { data = JSON.parse(e.data); } catch {}
    handlers[type]?.(data);
  };
  const connect = () => {
    es = new EventSource(`/api/jobs/${jobId}/events`);
    ["stage", "log", "preview", "done", "error"].forEach((t) => es.addEventListener(t, onMsg(t)));
    es.addEventListener("done", stop);
    es.addEventListener("error", (e) => {
      if (e && e.data) return; // 서버 error 이벤트
      if (closed) return;
      es.close();
      if (retries++ < 3) setTimeout(connect, 600);
      else startPolling();
    });
  };
  const startPolling = () => {
    pollTimer = setInterval(async () => {
      try {
        const d = await getJob(jobId);
        (d.stages || []).forEach((ev) => handlers[ev.type]?.(ev));
        if (["succeeded", "failed", "cancelled"].includes(d.status)) {
          handlers[d.status === "succeeded" ? "done" : "error"]?.({});
          stop();
        }
      } catch {}
    }, 1500);
  };
  connect();
  return stop;
}
