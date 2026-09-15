const LAB_KEY = "huicha_lab";

export const ROLE_REVIEWER = "合规复核";

export function readLabMode() {
  try {
    const q = new URLSearchParams(window.location.search);
    if (q.get("lab") === "1") {
      localStorage.setItem(LAB_KEY, "1");
      return true;
    }
    if (q.get("lab") === "0") {
      localStorage.removeItem(LAB_KEY);
      return false;
    }
    return localStorage.getItem(LAB_KEY) === "1";
  } catch {
    return false;
  }
}

export function persistLabMode(on) {
  try {
    const url = new URL(window.location.href);
    if (on) {
      localStorage.setItem(LAB_KEY, "1");
      url.searchParams.set("lab", "1");
    } else {
      localStorage.removeItem(LAB_KEY);
      url.searchParams.delete("lab");
    }
    window.history.replaceState({}, "", url);
  } catch {
    /* ignore */
  }
}

export function isReviewer(user) {
  return user?.role === ROLE_REVIEWER;
}

export function caseNo(alertId, createdAt = "") {
  const parts = String(alertId || "").split("-");
  if (parts.length >= 3 && parts[0] === "ALT") return `${parts[parts.length - 1]}-${parts[1]}`;
  const date = String(createdAt || "").slice(0, 10).replace(/-/g, "");
  return date || String(alertId || "");
}

export function maskAccount(acct) {
  const s = String(acct || "");
  if (s.startsWith("6222") && s.length >= 8) return `${s.slice(0, 4)}****${s.slice(-4)}`;
  return s;
}

export function displayName(name) {
  const text = String(name || "");
  return text.replace(/（演示）/g, "").replace(/（合成）/g, "").replace(/演示/g, "").trim() || text;
}

export const TODO_STATUSES = new Set(["pending", "investigating", "pending_review"]);
export const DONE_STATUSES = new Set(["closed", "monitoring", "ready_to_file", "modified"]);
