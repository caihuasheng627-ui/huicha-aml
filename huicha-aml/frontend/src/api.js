const API = "";
const INVESTIGATE_TIMEOUT_MS = 90000;
const TOKEN_KEY = "huicha_demo_token";
const SESSION_KEY = "huicha_session";
const USER_KEY = "huicha_user";

export function getDemoToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setDemoToken(token) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export function getSessionToken() {
  try {
    return sessionStorage.getItem(SESSION_KEY) || "";
  } catch {
    return "";
  }
}

export function getStoredUser() {
  try {
    const raw = sessionStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setSession(token, user) {
  try {
    if (token) sessionStorage.setItem(SESSION_KEY, token);
    else sessionStorage.removeItem(SESSION_KEY);
    if (user) sessionStorage.setItem(USER_KEY, JSON.stringify(user));
    else sessionStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
}

export function clearSession() {
  setSession("", null);
}

async function readError(r, fallback) {
  try {
    const data = await r.json();
    if (typeof data?.detail === "string") return data.detail;
  } catch {
    /* ignore */
  }
  return fallback;
}

function mapFetchError(e, fallback) {
  if (e?.name === "AbortError") return new Error("请求超时，请重试");
  if (e instanceof Error && e.message && !e.message.includes("fetch")) return e;
  return new Error(fallback);
}

async function request(path, { method = "GET", headers, body, timeoutMs, signal } = {}) {
  const ctrl = new AbortController();
  const onAbort = () => ctrl.abort();
  if (signal) {
    if (signal.aborted) ctrl.abort();
    else signal.addEventListener("abort", onAbort);
  }
  const timer = timeoutMs ? setTimeout(() => ctrl.abort(), timeoutMs) : null;
  try {
    const r = await fetch(`${API}${path}`, {
      method,
      headers: {
        ...(getDemoToken() ? { "X-Huicha-Token": getDemoToken() } : {}),
        ...(getSessionToken() ? { "X-Huicha-Session": getSessionToken() } : {}),
        ...headers,
      },
      body,
      signal: ctrl.signal,
    });
    return r;
  } catch (e) {
    throw mapFetchError(e, "无法连接调查服务");
  } finally {
    if (timer) clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onAbort);
  }
}

export async function fetchAlerts() {
  const r = await request("/api/alerts");
  if (!r.ok) throw new Error(await readError(r, "无法加载告警"));
  return r.json();
}

export async function fetchDetail(id, { signal } = {}) {
  const r = await request(`/api/alerts/${id}`, { signal });
  if (!r.ok) throw new Error(await readError(r, "无法加载案件"));
  return r.json();
}

export async function fetchHealth() {
  const r = await request("/api/health");
  if (!r.ok) throw new Error(await readError(r, "无法加载健康检查"));
  return r.json();
}

export async function fetchMetrics() {
  const r = await request("/api/metrics");
  if (!r.ok) throw new Error(await readError(r, "无法加载指标"));
  return r.json();
}

export async function fetchFeedback() {
  const r = await request("/api/feedback");
  if (!r.ok) throw new Error(await readError(r, "无法加载反馈看板"));
  return r.json();
}

export async function fetchAuthAccounts() {
  const r = await request("/api/auth/accounts");
  if (!r.ok) throw new Error(await readError(r, "无法加载演示账号"));
  return r.json();
}

export async function login(staffId, password) {
  const r = await request("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ staff_id: staffId, password }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "登录失败");
  setSession(data.token, data.user);
  return data;
}

export async function logout() {
  try {
    await request("/api/auth/logout", { method: "POST" });
  } catch {
    /* ignore */
  }
  clearSession();
}

export async function fetchMe() {
  const r = await request("/api/auth/me");
  if (!r.ok) {
    clearSession();
    throw new Error(await readError(r, "未登录"));
  }
  const data = await r.json();
  if (data?.user) setSession(getSessionToken(), data.user);
  return data;
}

export async function runInvestigate(id, { useChallenger = true, injectHallucination = false } = {}) {
  const q = new URLSearchParams({
    use_challenger: String(useChallenger),
    inject_hallucination: String(injectHallucination),
  });
  const r = await request(`/api/alerts/${id}/investigate?${q}`, {
    method: "POST",
    timeoutMs: INVESTIGATE_TIMEOUT_MS,
  });
  if (!r.ok) throw new Error(await readError(r, "调查失败"));
  return r.json();
}

export async function decide(id, decision, note) {
  const r = await request(`/api/alerts/${id}/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, note }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "处置失败");
  return data;
}

export async function downloadExport(id) {
  const r = await request(`/api/alerts/${id}/export`);
  if (!r.ok) throw new Error(await readError(r, "无法导出底稿"));
  const blob = await r.blob();
  const dispo = r.headers.get("content-disposition") || "";
  const star = /filename\*=UTF-8''([^;]+)/i.exec(dispo);
  const plain = /filename="([^"]+)"/i.exec(dispo);
  const name = decodeURIComponent(star?.[1] || plain?.[1] || `huicha-${id}.md`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function fetchKnowledge(q = "") {
  const r = await request(`/api/kb?q=${encodeURIComponent(q)}`);
  if (!r.ok) throw new Error(await readError(r, "无法加载知识库"));
  return r.json();
}
