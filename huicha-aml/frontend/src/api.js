const API = "";

async function readError(r, fallback) {
  try {
    const data = await r.json();
    if (typeof data?.detail === "string") return data.detail;
  } catch {
    /* ignore */
  }
  return fallback;
}

export async function fetchAlerts() {
  const r = await fetch(`${API}/api/alerts`);
  if (!r.ok) throw new Error(await readError(r, "无法加载告警"));
  return r.json();
}

export async function fetchDetail(id) {
  const r = await fetch(`${API}/api/alerts/${id}`);
  if (!r.ok) throw new Error(await readError(r, "无法加载案件"));
  return r.json();
}

export async function fetchHealth() {
  const r = await fetch(`${API}/api/health`);
  if (!r.ok) throw new Error(await readError(r, "无法加载健康检查"));
  return r.json();
}

export async function fetchMetrics() {
  const r = await fetch(`${API}/api/metrics`);
  if (!r.ok) throw new Error(await readError(r, "无法加载指标"));
  return r.json();
}

export async function fetchFeedback() {
  const r = await fetch(`${API}/api/feedback`);
  if (!r.ok) throw new Error(await readError(r, "无法加载反馈看板"));
  return r.json();
}

export async function runInvestigate(id, { useChallenger = true, injectHallucination = false } = {}) {
  const q = new URLSearchParams({
    use_challenger: String(useChallenger),
    inject_hallucination: String(injectHallucination),
  });
  const r = await fetch(`${API}/api/alerts/${id}/investigate?${q}`, { method: "POST" });
  if (!r.ok) throw new Error(await readError(r, "调查失败"));
  return r.json();
}

export async function decide(id, decision, note) {
  const r = await fetch(`${API}/api/alerts/${id}/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, note }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "处置失败");
  return data;
}

export function exportUrl(id) {
  return `${API}/api/alerts/${id}/export`;
}

export async function fetchKnowledge(q = "") {
  const r = await fetch(`${API}/api/kb?q=${encodeURIComponent(q)}`);
  if (!r.ok) throw new Error(await readError(r, "无法加载知识库"));
  return r.json();
}
