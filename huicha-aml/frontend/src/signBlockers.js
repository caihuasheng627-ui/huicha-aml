export function hardFactIssues(inv) {
  return (inv?.fact_issues || []).filter((row) => (row?.severity || "hard") !== "soft");
}

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
  if (hardFactIssues(inv).length) {
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

export function blockedSignNoteHint(inv) {
  if (!inv || inv.can_sign) return "";
  return `${signBlockerText(inv)}。不能直接签发，把人工判断写入草稿备注。`;
}

export function workingNoteText(text) {
  const raw = String(text || "");
  const idx = raw.indexOf("【补证清单】");
  return (idx < 0 ? raw : raw.slice(0, idx)).trim();
}

export function checklistNoteText(text) {
  const raw = String(text || "");
  const idx = raw.indexOf("【补证清单】");
  return idx < 0 ? "" : raw.slice(idx).trim();
}

export function scrollToDraft() {
  document.getElementById("report-draft")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export function noteHistory(inv) {
  const rows = (inv?.human_review?.notes || []).filter((row) => String(row?.text || "").trim());
  return rows;
}

export function noteTemplateFor(inv) {
  if (!inv || inv.can_sign) return "";
  const codes = new Set(collectSignBlockers(inv).map((row) => row.code));
  if (codes.has("rule_judge_conflict_low_conf")) {
    return "规则对照与 AI 建议分歧。我的判断是：……。依据：……。";
  }
  if (codes.has("fact_check")) {
    return "事实回查未通过的编号已人工核对：……。维持原判断/改为……。";
  }
  if (codes.has("cf_invalid") || codes.has("cf_not_dependent")) {
    return "证据充分性存疑。已复核必要证据：……。判断：……。";
  }
  if (
    codes.has("judge_contract") ||
    codes.has("missing_predicate") ||
    codes.has("predicate_failed") ||
    codes.has("citation_failed")
  ) {
    return "证据契约未过。已补看材料：……。人工判断：……。";
  }
  return "不能直接签发。人工判断：……。已核材料：……。";
}
