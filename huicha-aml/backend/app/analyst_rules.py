"""Analyst 规则打底。LLM 不在这里写最终分。"""

from __future__ import annotations

from .tools import PEER_BASELINE, peer_labels_from_graph, yuan

CONCLUSION_LABEL = {
    "exclude": "排除",
    "observe": "继续观察",
    "suggest_report": "建议上报",
}


def near_threshold(amount: float, band: float = 50000, ratio: float = 0.9) -> bool:
    return band * ratio <= amount < band


def score_to_conclusion(score: float) -> str:
    if score < 0.35:
        return "exclude"
    if score < 0.55:
        return "observe"
    return "suggest_report"


def rule_prior(
    *,
    use_challenger: bool,
    customer: dict,
    in_labels: list[str],
    out_labels: list[str],
    baseline: dict,
    kb_hits: list[dict],
    txs: list[dict],
) -> tuple[float, list[dict]]:
    if not use_challenger:
        return 0.0, []
    prior = 0.0
    hints: list[dict] = []
    if (
        customer["kind"] == "enterprise"
        and customer["industry"] in PEER_BASELINE
        and customer["industry"] != "贸易代理"
        and customer["kyc_level"] not in {"高风险", "关注"}
        and in_labels
        and out_labels
    ):
        prior -= 0.30
        peers = "、".join((in_labels + out_labels)[:4])
        detail = (
            f"{baseline['peer_note']} 开户于 {customer['opened_at']}，"
            f"KYC 为{customer['kyc_level']}，主要对手方为{peers}。"
        )
        ind_hit = next((h for h in kb_hits if h["kind"] == "industry"), None)
        if ind_hit:
            detail += f" 可引用 {ind_hit['id']}"
        hints.append({"title": "经营合理性（规则先验）", "detail": detail})
    if customer["kind"] == "individual" and customer["industry"] == "个人-退休":
        remarks = " ".join(t.get("remark") or "" for t in txs)
        registered = any(t.get("to_account", "").startswith("RELATIVE-") for t in txs) or "子女" in remarks
        if registered:
            prior -= 0.20
            hints.append(
                {
                    "title": "用途可解释（规则先验）",
                    "detail": f"档案：「{(customer.get('summary') or '')[:80]}」。备注含亲属/购房用途。",
                }
            )
        else:
            prior -= 0.08
            hints.append(
                {
                    "title": "退休客户但对手未完全核验（规则先验）",
                    "detail": "养老金客户大额转出，对手登记不完整，仅作弱开脱。",
                }
            )
    if customer["industry"] == "餐饮":
        prior -= 0.18
        hints.append({"title": "业态抗辩（规则先验）", "detail": baseline["peer_note"]})
    if not hints:
        hints.append(
            {
                "title": "未找到强规则先验",
                "detail": "开户时间短、行业与资金规模不匹配，或对手方分散后突然收口。",
            }
        )
    return round(prior, 4), hints


def analyze(
    *,
    alert: dict,
    customer: dict,
    txs: list[dict],
    account_id: str,
    baseline: dict,
    watch_hits: list[dict],
    graph: dict,
) -> dict:
    inflow = [t for t in txs if t["to_account"] == account_id]
    outflow = [t for t in txs if t["from_account"] == account_id]
    in_accounts = {t["from_account"] for t in inflow}
    near = [t for t in inflow if near_threshold(t["amount"])]
    night_out = [t for t in outflow if t["occurred_at"][11:13] >= "21" or t["occurred_at"][11:13] < "06"]
    findings: list[dict] = []
    risk_factors: list[dict] = [
        {"code": "base-risk", "label": "起始待查分", "delta": 0.12, "evidence_ids": [], "source": "rule", "tag": None}
    ]
    score = 0.12
    in_labels = peer_labels_from_graph(graph, account_id, txs, "in")
    out_labels = peer_labels_from_graph(graph, account_id, txs, "out")

    if "大额" in alert["alert_type"] or "频繁" in alert["alert_type"]:
        score += 0.44
        findings.append(
            {
                "code": "upstream-alert",
                "title": "上游监测命中大额/频繁",
                "detail": f"检测系统因「{alert['alert_type']}」生成告警，金额{yuan(alert['amount'])}。是否误报需用行业基线与对手方验证。",
                "evidence_ids": [t["id"] for t in txs[:4]],
            }
        )
        risk_factors.append(
            {
                "code": "upstream-alert",
                "label": "上游大额/频繁",
                "delta": 0.44,
                "evidence_ids": [t["id"] for t in txs[:4]],
                "source": "rule",
                "tag": "high_velocity",
            }
        )

    if "拆分" in alert["alert_type"] or "归集" in alert["alert_type"]:
        score += 0.16
        risk_factors.append(
            {
                "code": "alert-typology",
                "label": "告警类型拆分/归集",
                "delta": 0.16,
                "evidence_ids": [t["id"] for t in txs[:3]],
                "source": "rule",
                "tag": "structuring" if "拆分" in alert["alert_type"] else "suspicious_network",
            }
        )

    if (
        customer["kind"] == "enterprise"
        and customer["industry"] in PEER_BASELINE
        and len(in_labels) >= 1
        and len(out_labels) >= 1
        and customer["industry"] != "贸易代理"
    ):
        down = "、".join(in_labels[:3])
        up = "、".join(out_labels[:3])
        findings.append(
            {
                "code": "pattern-peer",
                "title": "交易与同业经营特征对照",
                "detail": (
                    f"流入对手方主要为{down}，流出对手方主要为{up}；"
                    f"样本流入{yuan(baseline['sample_in_sum'])}，约为同业月度区间的 {baseline['in_sum_vs_peer']} 倍。"
                    f"基线说明：{baseline['peer_note']}"
                ),
                "evidence_ids": [t["id"] for t in txs[:6]],
            }
        )

    if len(near) >= 8:
        score += 0.38
        findings.append(
            {
                "code": "structuring",
                "title": "疑似拆分存入以规避大额申报阈值",
                "detail": f"近窗有 {len(near)} 笔流入落在 4.9 万–5 万区间（如{yuan(near[0]['amount'])}，记录 {near[0]['id']}），随后出现集中转出。",
                "evidence_ids": [t["id"] for t in near[:8]] + [t["id"] for t in outflow],
            }
        )
        risk_factors.append(
            {
                "code": "structuring",
                "label": "拆分存入",
                "delta": 0.38,
                "evidence_ids": [t["id"] for t in near[:8]],
                "source": "rule",
                "tag": "structuring",
            }
        )

    if len(in_accounts) >= 4 and customer["kind"] == "enterprise":
        score += 0.22
        findings.append(
            {
                "code": "funnel",
                "title": "多个个人账户向新设企业归集",
                "detail": f"流入对手方 {len(in_accounts)} 个，开户日 {customer['opened_at']}，KYC 为{customer['kyc_level']}。",
                "evidence_ids": [t["id"] for t in inflow],
            }
        )
        risk_factors.append(
            {
                "code": "funnel",
                "label": "多账户归集",
                "delta": 0.22,
                "evidence_ids": [t["id"] for t in inflow],
                "source": "rule",
                "tag": "suspicious_network",
            }
        )

    if watch_hits:
        score += 0.18
        findings.append(
            {
                "code": "watchlist",
                "title": "对手方命中演示关注名单",
                "detail": "、".join(h["name"] for h in watch_hits) + " 出现在流出路径中。",
                "evidence_ids": [t["id"] for t in outflow],
            }
        )
        risk_factors.append(
            {
                "code": "watchlist",
                "label": "名单命中",
                "delta": 0.18,
                "evidence_ids": [t["id"] for t in outflow],
                "source": "rule",
                "tag": "suspicious_network",
            }
        )

    if night_out and outflow:
        score += 0.08
        findings.append(
            {
                "code": "night-out",
                "title": "存在夜间集中转出",
                "detail": f"流出发生在 {outflow[-1]['occurred_at']}，记录 {outflow[-1]['id']}，金额{yuan(outflow[-1]['amount'])}。",
                "evidence_ids": [t["id"] for t in night_out],
            }
        )
        risk_factors.append(
            {
                "code": "night-out",
                "label": "夜间集中转出",
                "delta": 0.08,
                "evidence_ids": [t["id"] for t in night_out],
                "source": "rule",
                "tag": "rapid_transfer",
            }
        )

    unk_out = [t for t in outflow if str(t.get("to_account", "")).startswith("UNK-")]
    if unk_out and customer["industry"] == "个人-退休":
        score += 0.10
        findings.append(
            {
                "code": "unregistered-counterparty",
                "title": "大额转至未登记对手",
                "detail": f"存在流向未登记账户的交易（如 {unk_out[0]['id']}），用途待尽调核实。",
                "evidence_ids": [t["id"] for t in unk_out],
            }
        )
        risk_factors.append(
            {
                "code": "unregistered-counterparty",
                "label": "未登记对手",
                "delta": 0.10,
                "evidence_ids": [t["id"] for t in unk_out],
                "source": "rule",
                "tag": "mule_account",
            }
        )

    hops = sorted(txs, key=lambda t: t.get("occurred_at") or "")
    hop_nodes = {t.get("from_account") for t in hops} | {t.get("to_account") for t in hops}
    if "多层" in (alert.get("alert_type") or "") and len(hops) >= 3 and len(hop_nodes) >= 3:
        hop_ids = [t["id"] for t in hops[:4]]
        score += 0.10
        findings.append(
            {
                "code": "layering",
                "title": "短时多层资金转移",
                "detail": (
                    f"近窗 {len(hops)} 笔途经 {len(hop_nodes)} 个账户，"
                    f"{hops[0]['from_account']} → … → {hops[-1]['to_account']}，"
                    f"首笔 {hops[0]['id']} {hops[0]['occurred_at']}，末笔 {hops[-1]['id']} {hops[-1]['occurred_at']}。"
                ),
                "evidence_ids": hop_ids,
            }
        )
        risk_factors.append(
            {
                "code": "layering",
                "label": "多层转移",
                "delta": 0.10,
                "evidence_ids": hop_ids,
                "source": "rule",
                "tag": "layering",
            }
        )

    if not findings:
        findings.append(
            {
                "code": "thin",
                "title": "未形成典型可疑模式",
                "detail": "交易笔数或对手方不足以支持上报，建议结合柜面用途说明观察或排除。",
                "evidence_ids": [t["id"] for t in txs[:3]],
            }
        )

    return {
        "findings": findings,
        "risk_factors": risk_factors,
        "score": score,
        "in_labels": in_labels,
        "out_labels": out_labels,
        "inflow": inflow,
        "outflow": outflow,
    }
