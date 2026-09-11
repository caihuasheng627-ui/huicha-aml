"""Reporter 草稿模板。润色仍走 llm.enrich_report_reason。"""

from __future__ import annotations

from .analyst_rules import CONCLUSION_LABEL
from .tools import yuan


def render_report(
    alert,
    customer,
    baseline,
    findings,
    challenger,
    conclusion,
    txs,
    inflow,
    outflow,
    use_challenger,
    kb_hits,
) -> dict:
    in_sum = round(sum(t["amount"] for t in inflow), 2)
    out_sum = round(sum(t["amount"] for t in outflow), 2)
    sample_ids = "、".join(t["id"] for t in (inflow + outflow)[:6]) or "（无交易）"
    behavior = (
        f"客户{customer['name']}（客户号 {customer['id']}，账户 {alert['account_id']}）"
        f"于告警日 {alert['created_at']} 触发「{alert['alert_type']}」。"
        f"近窗流入 {len(inflow)} 笔合计{yuan(in_sum)}，流出 {len(outflow)} 笔合计{yuan(out_sum)}。"
        f"行业登记为{customer['industry']}，开户日期 {customer['opened_at']}。"
        f"上游来源：{alert['upstream']}。"
    )
    suspicion = "；".join(f"{f['title']}（证据 {', '.join(f['evidence_ids'][:4])}）" for f in findings)
    if challenger:
        challenge = "；".join(
            f"{c.get('claim') or c['title']}(Δ{c.get('delta', 0):+.2f}): {c['detail']}" for c in challenger
        )
    else:
        challenge = "本轮未启用 Challenger。"
    cite_reg = "、".join(h["id"] for h in kb_hits if h["kind"] == "regulation") or "KB-REG-03"
    cite_all = "、".join(h["id"] for h in kb_hits[:5]) or "（无）"
    if conclusion == "exclude":
        reason = (
            f"{'综合 Challenger 意见，' if use_challenger else ''}"
            f"交易与{customer['industry']}经营特征及基线说明「{baseline['peer_note']}」相符，"
            f"建议排除。依据 {cite_reg}，排除理由已记录。关键交易编号：{sample_ids}。"
        )
    elif conclusion == "observe":
        reason = (
            f"存在疑点但尚不充分，建议继续观察并补充尽调。"
            f"依据 {cite_reg}，要素仍须写全。关键交易编号：{sample_ids}。"
        )
    else:
        reason = (
            f"疑点分析认为资金或行为特征与客户身份不匹配，建议按内部规程复核后提交可疑交易报告。"
            f"依据 {cite_reg}，本草稿覆盖资金行为、疑点与理由，须人工签发后才能报送。"
            f"关键交易编号：{sample_ids}。"
        )
    full = "\n".join(
        [
            f"【资金交易及客户行为】{behavior}",
            f"【疑点分析】{suspicion}",
            f"【反证】{challenge}",
            f"【结论与理由】{CONCLUSION_LABEL[conclusion]}。{reason}",
            f"【知识库引用】{cite_all}",
        ]
    )
    return {
        "behavior": behavior,
        "suspicion": suspicion,
        "challenge": challenge,
        "reason": reason,
        "full_text": full,
        "sample_ids": sample_ids,
        "elements": [
            {"key": "报告触发点", "value": alert["alert_type"]},
            {"key": "资金交易及客户行为", "value": behavior},
            {"key": "疑点分析", "value": suspicion},
            {"key": "可疑/排除理由", "value": reason},
            {"key": "知识库引用", "value": cite_all},
        ],
    }


def apply_reason(report: dict, polished: str, conclusion: str) -> None:
    report["reason"] = polished
    report["elements"] = [
        e if e["key"] != "可疑/排除理由" else {"key": e["key"], "value": polished} for e in report["elements"]
    ]
    rebuilt = []
    for line in report["full_text"].split("\n"):
        if line.startswith("【结论与理由】"):
            rebuilt.append(f"【结论与理由】{CONCLUSION_LABEL[conclusion]}。{polished}")
        else:
            rebuilt.append(line)
    report["full_text"] = "\n".join(rebuilt)
