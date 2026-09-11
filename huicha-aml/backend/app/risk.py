"""可解释风险聚合。LLM 不得直接写最终分。"""

from __future__ import annotations

from .schema import Recommendation, RiskLevel

CONCLUSION_TO_RECO: dict[str, Recommendation] = {
    "exclude": "CLOSE",
    "observe": "MONITOR",
    "suggest_report": "REPORT_REVIEW",
}

RECO_LABEL = {
    "CLOSE": "建议关闭（排除）",
    "MONITOR": "建议持续监测",
    "EDD": "建议加强尽调",
    "REPORT_REVIEW": "建议进入上报复核（须人签）",
}


def score_to_conclusion(score: float) -> str:
    if score < 0.35:
        return "exclude"
    if score < 0.55:
        return "observe"
    return "suggest_report"


def score_to_level(score: float) -> RiskLevel:
    if score < 0.35:
        return "LOW"
    if score < 0.55:
        return "MEDIUM"
    return "HIGH"


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def aggregate(factors: list[dict], *, challenger_delta: float = 0.0) -> dict:
    base = 0.0
    parts = []
    for f in factors:
        d = float(f.get("delta") or 0)
        base += d
        parts.append(
            {
                "code": f.get("code"),
                "label": f.get("label"),
                "delta": round(d, 4),
                "evidence_ids": list(f.get("evidence_ids") or []),
                "source": f.get("source") or "rule",
                "tag": f.get("tag"),
            }
        )
    raw = base + float(challenger_delta)
    final = clamp01(raw)
    # 与旧切档兼容：历史演示用 0.05–0.95 夹紧
    display = max(0.05, min(0.95, final if final not in (0.0, 1.0) else max(0.05, min(0.95, raw))))
    if raw < 0.05:
        display = 0.05
    if raw > 0.95:
        display = 0.95
    conclusion = score_to_conclusion(display)
    return {
        "factors": parts,
        "challenger_delta": round(float(challenger_delta), 4),
        "raw": round(raw, 4),
        "final": round(display, 4),
        "conclusion": conclusion,
        "recommendation": CONCLUSION_TO_RECO[conclusion],
        "recommendation_label": RECO_LABEL[CONCLUSION_TO_RECO[conclusion]],
        "risk_level": score_to_level(display),
        "note": "分数由规则因子 + 校验后 Challenger delta 合成；不是监管结论。",
    }


def counterfactual(factors: list[dict], drop_codes: list[str], *, challenger_delta: float = 0.0) -> dict:
    kept = [f for f in factors if f.get("code") not in set(drop_codes)]
    alt = aggregate(kept, challenger_delta=challenger_delta)
    orig = aggregate(factors, challenger_delta=challenger_delta)
    return {
        "dropped": drop_codes,
        "original": orig["final"],
        "counterfactual": alt["final"],
        "difference": round(orig["final"] - alt["final"], 4),
        "assumption": f"若去掉因子 {','.join(drop_codes) or '（无）'} 后重算",
        "alt_conclusion": alt["conclusion"],
        "data_note": "rule-based counterfactual, synthetic",
    }
