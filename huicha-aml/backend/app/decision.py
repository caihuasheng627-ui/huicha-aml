"""证据约束的 AI 建议、确定性校验与政策护栏。"""

from __future__ import annotations

import re

from .analyst_rules import score_to_conclusion
from .risk import CONCLUSION_TO_RECO, RECO_LABEL
from .schema import JudgeDecision

DISPOSITIONS = {"exclude", "observe", "suggest_report"}

# missing_evidence 应是「尚未取得的材料」的自然语言描述；模型偶尔会把证据编号塞进去。
ID_LIKE_RE = re.compile(
    r"^(?:EV|TX|KB|ALT|ACC|ACCOUNT|CASH|POS|UNK|RELATIVE|CLIENT)[-_][A-Z0-9\-_]+$|^C-[A-Z0-9]+$",
    re.I,
)
MAX_MISSING_EVIDENCE = 8


def _is_id_like(text: str, known_ids: set[str]) -> bool:
    token = text.strip()
    if not token:
        return True
    if token in known_ids:
        return True
    if ID_LIKE_RE.match(token):
        return True
    # 「EV-…-001至030」这类编号区间同样不是材料描述。
    return bool(re.fullmatch(r"[A-Z]{2,7}-[A-Z0-9\-]+\s*(?:至|到|~|-)\s*[A-Z0-9\-]+", token, re.I))


def sanitize_missing_evidence(items: list, *, known_ids: set[str] | None = None) -> tuple[list[str], list[str]]:
    known = known_ids or set()
    kept: list[str] = []
    dropped: list[str] = []
    for item in items or []:
        text = str(item or "").strip()
        if not text:
            continue
        if _is_id_like(text, known):
            dropped.append(text)
        elif text not in kept:
            kept.append(text)
    return kept[:MAX_MISSING_EVIDENCE], dropped


def rule_baseline(analyst: dict) -> dict:
    """规则只提供透明对照，不与 AI 分数合成。"""
    score = max(0.05, min(0.95, float(analyst.get("score") or 0)))
    conclusion = score_to_conclusion(score)
    return {
        "score": round(score, 4),
        "conclusion": conclusion,
        "recommendation": CONCLUSION_TO_RECO[conclusion],
        "recommendation_label": RECO_LABEL[CONCLUSION_TO_RECO[conclusion]],
        "factors": analyst.get("risk_factors") or [],
        "note": "仅按本案流水重新计算的规则对照，不读取上游告警标签加分，也不决定最终建议。",
    }


def normalize_judge(raw: dict, *, known_ids: set[str] | None = None) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Judge 输出不是 JSON 对象")
    data = dict(raw)
    data["disposition"] = str(data.get("disposition") or "").strip()
    try:
        data["confidence"] = float(data.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Judge confidence 无法解析") from exc
    for key in (
        "typologies",
        "supporting_evidence_ids",
        "contradicting_evidence_ids",
        "missing_evidence",
        "next_actions",
    ):
        value = data.get(key)
        data[key] = value if isinstance(value, list) else []
    rationale = data.get("rationale")
    if isinstance(rationale, str):
        rationale = [{"text": rationale, "evidence_ids": data["supporting_evidence_ids"]}]
    data["rationale"] = rationale if isinstance(rationale, list) else []
    data["missing_evidence"], dropped = sanitize_missing_evidence(data["missing_evidence"], known_ids=known_ids)
    result = JudgeDecision.model_validate(data).model_dump()
    if dropped:
        result["sanitized_missing_evidence"] = dropped
    return result


def verify_judge(decision: dict, *, allowed_evidence: set[str]) -> dict:
    """每个实质理由必须有本案引用；缺引用或伪造引用时整份建议不可采纳。"""
    issues: list[dict] = []
    cited: list[str] = []
    for key in ("supporting_evidence_ids", "contradicting_evidence_ids"):
        for evidence_id in decision.get(key) or []:
            if evidence_id not in cited:
                cited.append(evidence_id)
    for index, row in enumerate(decision.get("rationale") or []):
        ids = [str(x) for x in (row.get("evidence_ids") or []) if str(x)]
        if not str(row.get("text") or "").strip():
            issues.append({"kind": "empty_rationale", "index": index, "message": "理由为空"})
        if not ids:
            issues.append({"kind": "uncited_rationale", "index": index, "message": "理由缺少证据编号"})
        for evidence_id in ids:
            if evidence_id not in cited:
                cited.append(evidence_id)
    invalid = [evidence_id for evidence_id in cited if evidence_id not in allowed_evidence]
    if invalid:
        issues.append(
            {
                "kind": "invalid_citation",
                "evidence_ids": invalid,
                "message": f"引用不属于本案工具结果：{','.join(invalid[:6])}",
            }
        )
    if not decision.get("rationale"):
        issues.append({"kind": "missing_rationale", "message": "缺少结构化理由"})
    if decision.get("disposition") == "suggest_report" and not decision.get("supporting_evidence_ids"):
        issues.append({"kind": "missing_support", "message": "建议上报但没有支持证据"})
    return {
        "passed": not issues,
        "issues": issues,
        "citation_count": len(cited),
        "invalid_ids": invalid,
        "score_kind": "evidence_contract",
        "reason": "结构化建议及逐条引用通过校验" if not issues else "Judge 输出未通过证据契约",
    }


def apply_guardrails(decision: dict, *, watch_hits: list[dict], fact_issues: list[dict] | None = None) -> dict:
    """规则只作不可绕过的政策边界，不参与加权打分。"""
    proposed = decision["disposition"]
    final = proposed
    checks = [
        {
            "code": "human-approval",
            "label": "任何建议均须人工签发",
            "triggered": True,
            "effect": "禁止自动报送",
        }
    ]
    if watch_hits and final == "exclude":
        final = "observe"
        checks.append(
            {
                "code": "watchlist-no-close",
                "label": "名单命中不得直接排除",
                "triggered": True,
                "effect": "最低提升为继续观察",
            }
        )
    if fact_issues:
        checks.append(
            {
                "code": "fact-check-block",
                "label": "事实回查失败不得签发",
                "triggered": True,
                "effect": "阻断签发",
            }
        )
    return {
        "proposed_conclusion": proposed,
        "final_conclusion": final,
        "overridden": final != proposed,
        "checks": checks,
        "recommendation": CONCLUSION_TO_RECO[final],
        "recommendation_label": RECO_LABEL[CONCLUSION_TO_RECO[final]],
        "note": "护栏仅执行政策否决/升级，不与模型做加权合成。",
    }


def decision_claims(decision: dict) -> list[dict]:
    rows = []
    for polarity, key in (
        ("support", "supporting_evidence_ids"),
        ("counter", "contradicting_evidence_ids"),
    ):
        ids = decision.get(key) or []
        if ids:
            rows.append(
                {
                    "claim": "支持建议的证据" if polarity == "support" else "反向或开脱证据",
                    "evidence_ids": ids,
                    "polarity": polarity,
                }
            )
    return rows
