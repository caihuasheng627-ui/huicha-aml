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


CONCLUSION_LABEL = {
    "exclude": "排除",
    "observe": "继续观察",
    "suggest_report": "建议上报",
}


def counterfactual(
    factors: list[dict],
    drop_codes: list[str] | None = None,
    *,
    challenger_delta: float = 0.0,
    drop_challenger: bool = False,
) -> dict:
    codes = [c for c in (drop_codes or []) if c]
    slots = 2 - (1 if drop_challenger else 0)
    if slots < 0:
        drop_challenger = False
        slots = 2
    codes = codes[: max(0, slots)]
    kept = [f for f in factors if f.get("code") not in set(codes)]
    alt_delta = 0.0 if drop_challenger else challenger_delta
    alt = aggregate(kept, challenger_delta=alt_delta)
    orig = aggregate(factors, challenger_delta=challenger_delta)
    names = []
    by_code = {f.get("code"): f for f in factors}
    for c in codes:
        names.append((by_code.get(c) or {}).get("label") or c)
    if drop_challenger:
        names.append("Challenger 调整")
    assumption = f"若无此疑点「{'、'.join(names) or '（未选）'}」"
    return {
        "dropped": codes,
        "drop_challenger": drop_challenger,
        "original": orig["final"],
        "counterfactual": alt["final"],
        "difference": round(orig["final"] - alt["final"], 4),
        "assumption": assumption,
        "original_conclusion": orig["conclusion"],
        "alt_conclusion": alt["conclusion"],
        "original_label": CONCLUSION_LABEL[orig["conclusion"]],
        "alt_label": CONCLUSION_LABEL[alt["conclusion"]],
        "original_recommendation": orig["recommendation"],
        "alt_recommendation": alt["recommendation"],
        "original_recommendation_label": orig["recommendation_label"],
        "alt_recommendation_label": alt["recommendation_label"],
        "data_note": "rule-based counterfactual, synthetic",
    }
