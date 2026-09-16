export function collectSignBlockers(inv) {
  if (!inv) return [];
  const rows = [];
  const push = (code, message) => {
    const text = String(message || "").trim();
    if (!text) return;
    if (rows.some((row) => row.code === code || row.message === text)) return;
    rows.push({ code: code || "block", message: text });
  };
  for (const row of inv.sign_blockers || []) {
    push(row.code, row.message);
  }
  if (inv.fact_issues?.length) {
    push("fact_check", "事实回查未通过");
  }
  const reliability = inv.agent_reliability || {};
  for (const row of reliability.reasons || []) {
    push(row.code, row.message);
  }
  if (inv.use_challenger !== false && inv.judge_validation && inv.judge_validation.passed === false) {
    push("judge_contract", inv.judge_validation.reason || "证据契约未通过");
  }
  return rows;
}

export function signBlockerText(inv, fallback = "当前结论不可直接签发") {
  const messages = collectSignBlockers(inv).map((row) => row.message);
  return messages.length ? messages.join("；") : fallback;
}

export function reliabilityStance(inv) {
  if (!inv || inv.use_challenger === false) return "committed";
  return inv.agent_reliability?.stance === "abstain" ? "abstain" : "committed";
}
