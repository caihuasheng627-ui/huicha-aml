from __future__ import annotations

import time

from sqlalchemy.orm import Session

from .knowledge import retrieve_for_alert
from .tools import collect_bundle, fact_check


CONCLUSION_LABEL = {
    "exclude": "排除",
    "observe": "继续观察",
    "suggest_report": "建议上报",
}

FAKE_ACCOUNT = "6222-FAKE-9999"


def yuan(n) -> str:
    n = float(n)
    if abs(n) >= 10000:
        s = f" {n / 10000:.2f} 万元"
        return s.replace(" 0 万元", " 0 元").replace(".00 万元", " 万元")
    return f" {n:,.0f} 元"


def _near_threshold(amount: float, band: float = 50000, ratio: float = 0.9) -> bool:
    return band * ratio <= amount < band


def _score_to_conclusion(score: float) -> str:
    if score < 0.35:
        return "exclude"
    if score < 0.55:
        return "observe"
    return "suggest_report"


def run_investigation(
    db: Session,
    alert_id: str,
    *,
    use_challenger: bool = True,
    inject_hallucination: bool = False,
) -> dict:
    started = time.perf_counter()
    bundle = collect_bundle(db, alert_id)
    alert = bundle["alert"]
    customer = bundle["customer"]
    txs = bundle["transactions"]
    baseline = bundle["baseline"]
    watch_hits = bundle["watch_hits"]
    account_id = alert["account_id"]

    steps = []
    tool_trace = []

    kb_hits = retrieve_for_alert(alert["alert_type"], customer["industry"])
    kb_ids = "、".join(h["id"] for h in kb_hits) or "（无命中）"

    plan = [
        "读取告警与上游检测来源",
        "调取客户 KYC 与开户信息",
        "抽取账户近窗交易",
        "检索制度、类型学与行业基线知识库",
        "计算行业行为基线偏离",
        "查询对手方一度关联与名单命中",
        "Analyst 模式分析",
        "Challenger 寻找反证" if use_challenger else "跳过 Challenger（消融）",
        "Reporter 按监管要素生成草稿并做事实回查",
    ]
    steps.append(
        {
            "role": "Planner",
            "title": "生成调查计划",
            "content": f"告警类型「{alert['alert_type']}」。先取数、检索知识库、再分析"
            + ("、再质疑" if use_challenger else "（本轮关闭质疑角色）")
            + "、最后写理由。结论由规则打分得出，不用案例标签锁死。",
            "items": plan,
        }
    )
    tool_trace.append({"tool": "get_alert", "ok": True, "records": 1})
    tool_trace.append({"tool": "search_knowledge", "ok": True, "records": len(kb_hits)})

    steps.append(
        {
            "role": "Collector",
            "title": "只读取数并留痕",
            "content": f"已拉取客户 {customer['name']}（{customer['id']}）、交易 {len(txs)} 笔、基线、一度对手方，以及知识库 {len(kb_hits)} 条。全部为只读工具。",
            "items": [
                f"KYC：{'对公' if customer['kind']=='enterprise' else '个人'} / {customer['industry']} / 开户 {customer['opened_at']}",
                f"样本流入{yuan(baseline['sample_in_sum'])}，流出{yuan(baseline['sample_out_sum'])}",
                f"关注名单命中 {len(watch_hits)} 个",
                f"知识库命中：{kb_ids}",
            ],
        }
    )
    tool_trace.extend(
        [
            {"tool": "get_customer", "ok": True, "records": 1},
            {"tool": "get_transactions", "ok": True, "records": len(txs)},
            {"tool": "get_baseline", "ok": True, "records": 1},
            {"tool": "get_graph", "ok": True, "records": len(bundle["graph"]["nodes"])},
            {"tool": "check_watchlist", "ok": True, "records": len(watch_hits)},
        ]
    )

    inflow = [t for t in txs if t["to_account"] == account_id]
    outflow = [t for t in txs if t["from_account"] == account_id]
    in_accounts = {t["from_account"] for t in inflow}
    near = [t for t in inflow if _near_threshold(t["amount"])]
    night_out = [t for t in outflow if t["occurred_at"][11:13] >= "21" or t["occurred_at"][11:13] < "06"]

    findings = []
    score = 0.12

    # 上游告警本身构成待验证疑点，不能靠 demo_tag 写死结论
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

    if "拆分" in alert["alert_type"] or "归集" in alert["alert_type"]:
        score += 0.16

    if customer["kind"] == "enterprise" and customer["industry"] == "日用百货批发":
        findings.append(
            {
                "code": "pattern-wholesale",
                "title": "交易与批发备货特征相符",
                "detail": f"下游余杭便利连锁反复入账、上游浙北日化供应中心反复出账，样本流入{yuan(baseline['sample_in_sum'])}，约为同业月度区间的 {baseline['in_sum_vs_peer']} 倍。",
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

    if not findings:
        findings.append(
            {
                "code": "thin",
                "title": "未形成典型可疑模式",
                "detail": "交易笔数或对手方不足以支持上报，建议结合柜面用途说明观察或排除。",
                "evidence_ids": [t["id"] for t in txs[:3]],
            }
        )

    steps.append(
        {
            "role": "Analyst",
            "title": "四类分析",
            "content": "已完成交易模式、关联网络、行为基线、名单命中扫描。"
            + (
                " 对照类型学：" + "、".join(h["title"] for h in kb_hits if h["kind"] == "typology")
                if any(h["kind"] == "typology" for h in kb_hits)
                else ""
            ),
            "items": [f"{f['title']}：{f['detail']}" for f in findings],
        }
    )

    challenger = []
    if use_challenger:
        if customer["industry"] == "日用百货批发":
            challenger.append(
                {
                    "title": "经营合理性抗辩",
                    "detail": f"{baseline['peer_note']} 开户于 {customer['opened_at']}，KYC 非高风险，对手方为长期上下游而非散户现金。",
                }
            )
            score -= 0.45
            ind_hit = next((h for h in kb_hits if h["id"] == "KB-IND-01"), None)
            if ind_hit:
                challenger[-1]["detail"] += f" 引用 {ind_hit['id']}：{ind_hit['snippet']}"
        if customer["kind"] == "individual" and customer["industry"] == "个人-退休":
            challenger.append(
                {
                    "title": "用途可解释",
                    "detail": "客户档案摘要记载子女购房，单笔柜面大额不一定构成洗钱，需核验收款人亲属关系后排除或观察。",
                }
            )
            score -= 0.22
        if customer["industry"] == "餐饮":
            challenger.append(
                {
                    "title": "业态抗辩",
                    "detail": baseline["peer_note"],
                }
            )
            score -= 0.28
        if not challenger:
            challenger.append(
                {
                    "title": "未找到强开脱理由",
                    "detail": "开户时间短、职业/行业与资金规模不匹配，或对手方分散后突然收口，反证不足。",
                }
            )
        steps.append(
            {
                "role": "Challenger",
                "title": "寻找反证，抑制确认偏误",
                "content": "对 Analyst 每条疑点尝试给出经营或用途解释，并回写置信度。",
                "items": [f"{c['title']}：{c['detail']}" for c in challenger],
            }
        )
    else:
        steps.append(
            {
                "role": "Challenger",
                "title": "本轮已关闭（消融）",
                "content": "仅保留 Analyst 疑点，用于对比：关掉质疑后，经营特征明显的误报更容易被建议上报。",
                "items": ["未执行反证，置信度未下调。"],
            }
        )

    score = max(0.05, min(0.95, score))
    conclusion = _score_to_conclusion(score)

    evidence = []
    for t in txs:
        evidence.append(
            {
                "id": t["id"],
                "type": "transaction",
                "from_account": t["from_account"],
                "to_account": t["to_account"],
                "amount": t["amount"],
                "occurred_at": t["occurred_at"],
                "channel": t["channel"],
                "remark": t["remark"],
                "summary": f"{t['occurred_at']} {t['from_account']} → {t['to_account']} {yuan(t['amount']).strip()}（{t['channel']} {t['remark']}）",
            }
        )
    evidence.append(
        {
            "id": customer["id"],
            "type": "kyc",
            "summary": f"{customer['name']}，{customer['industry']}，开户 {customer['opened_at']}，{customer['city']}",
        }
    )

    report = _render_report(
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
    )
    if inject_hallucination:
        poison = f"另发现未在工具结果中出现的对手账户 {FAKE_ACCOUNT}。"
        report["reason"] += poison
        report["full_text"] += "\n【注入幻觉演示】" + poison
        report["elements"].append({"key": "幻觉注入", "value": poison})
    issues = fact_check(report["full_text"], bundle["facts"])

    steps.append(
        {
            "role": "Reporter",
            "title": "监管要素草稿 + 事实回查",
            "content": "金额、账号、交易编号均须来自工具返回值。不匹配字段标红，不可签发。",
            "items": [
                f"建议结论：{CONCLUSION_LABEL[conclusion]}（置信度 {int(score * 100)}%）",
                f"事实回查问题数：{len(issues)}",
                f"知识库引用：{kb_ids}",
                f"Challenger：{'开启' if use_challenger else '关闭'}",
                "Agent 不可自动报送，须调查员签发。",
            ],
        }
    )

    return {
        "alert": alert,
        "customer": customer,
        "plan": plan,
        "steps": steps,
        "tool_trace": tool_trace,
        "findings": findings,
        "challenger": challenger,
        "use_challenger": use_challenger,
        "inject_hallucination": inject_hallucination,
        "conclusion": conclusion,
        "conclusion_label": CONCLUSION_LABEL[conclusion],
        "confidence": round(score, 2),
        "report": report,
        "evidence": evidence,
        "graph": bundle["graph"],
        "baseline": baseline,
        "watch_hits": watch_hits,
        "kb_hits": kb_hits,
        "transactions": txs,
        "fact_issues": issues,
        "can_sign": len(issues) == 0,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "comparison": {
            "agent_ms": int((time.perf_counter() - started) * 1000),
            "manual_minutes": 25 if conclusion == "exclude" else 90,
            "tools_called": len(tool_trace),
            "note": "人工分钟数为同业调查作业区间示意，非工行实测。",
        },
    }


def _render_report(
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
    challenge = "；".join(c["detail"] for c in challenger) if challenger else "本轮未启用 Challenger。"
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
        "elements": [
            {"key": "报告触发点", "value": alert["alert_type"]},
            {"key": "资金交易及客户行为", "value": behavior},
            {"key": "疑点分析", "value": suspicion},
            {"key": "可疑/排除理由", "value": reason},
            {"key": "知识库引用", "value": cite_all},
        ],
    }
