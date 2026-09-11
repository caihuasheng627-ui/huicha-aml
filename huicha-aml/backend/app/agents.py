from __future__ import annotations

import time

from sqlalchemy.orm import Session

from .case_store import persist_investigation
from .evidence import build_evidence_graph, source_ids_of
from .knowledge import retrieve_for_alert
from .llm import enrich_challenger, enrich_report_reason, llm_model
from .logging_util import audit, warning
from .privacy import PrivacyMap
from .prompts import prompt_version
from .risk import CONCLUSION_TO_RECO, RECO_LABEL, aggregate, counterfactual, score_to_level
from .schema import InvestigationPlan, PlanStep, RegulationCite, StructuredReport
from .tool_audit import bind_tool_context, reset_tool_context, tool
from .tools import (
    ALLOWED_TOOLS,
    PEER_BASELINE,
    collect_bundle,
    fact_check,
    get_accounts,
    get_related_accounts,
    get_timeline,
    peer_labels_from_graph,
    plan_tool_names,
    search_regulation,
    yuan,
)
from .typology import tags_from_findings
from .validator import filter_challenger_items

CONCLUSION_LABEL = {
    "exclude": "排除",
    "observe": "继续观察",
    "suggest_report": "建议上报",
}

FAKE_ACCOUNT = "6222-FAKE-9999"


def _near_threshold(amount: float, band: float = 50000, ratio: float = 0.9) -> bool:
    return band * ratio <= amount < band


def _score_to_conclusion(score: float) -> str:
    if score < 0.35:
        return "exclude"
    if score < 0.55:
        return "observe"
    return "suggest_report"


@tool("search_knowledge")
def search_knowledge_tool(alert_type: str, industry: str, as_of: str = "") -> list[dict]:
    return retrieve_for_alert(alert_type, industry, as_of=as_of)


def _rule_prior(
    *,
    use_challenger: bool,
    customer: dict,
    in_labels: list[str],
    out_labels: list[str],
    baseline: dict,
    kb_hits: list[dict],
    txs: list[dict],
) -> tuple[float, list[dict]]:
    """规则先验（有界）：仅在开启 Challenger 时生效，与 LLM delta 叠加。"""
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


def run_investigation(
    db: Session,
    alert_id: str,
    *,
    use_challenger: bool = True,
    inject_hallucination: bool = False,
) -> dict:
    started = time.perf_counter()
    tool_trace: list = []
    tokens = bind_tool_context(db=db, alert_id=alert_id, trace=tool_trace)
    try:
        return _run_investigation_inner(
            db,
            alert_id,
            use_challenger=use_challenger,
            inject_hallucination=inject_hallucination,
            started=started,
            tool_trace=tool_trace,
        )
    finally:
        reset_tool_context(tokens)


def _run_investigation_inner(
    db: Session,
    alert_id: str,
    *,
    use_challenger: bool,
    inject_hallucination: bool,
    started: float,
    tool_trace: list,
) -> dict:
    # 取数包：Planner 清单决定是否调用基线/图谱/名单（经 @tool 留痕）
    bundle = collect_bundle(db, alert_id)
    alert = bundle["alert"]
    customer = bundle["customer"]
    planned = bundle.get("planned_tools") or plan_tool_names(alert["alert_type"])
    as_of = (alert.get("created_at") or "")[:10]
    txs = bundle["transactions"]
    baseline = bundle["baseline"]
    watch_hits = bundle["watch_hits"]
    account_id = alert["account_id"]
    kb_hits = search_knowledge_tool(alert["alert_type"], customer["industry"], as_of)
    if "get_accounts" in planned:
        get_accounts(db, customer["id"])
    timeline = get_timeline(db, account_id, txs=txs) if "get_timeline" in planned else []
    if "get_related_accounts" in planned:
        peers = get_related_accounts(db, account_id, txs=txs)
        if len(peers) <= 4:
            seen = {t["id"] for t in txs}
            from .tools import get_transactions

            for p in peers:
                for extra in get_transactions(db, p["account_id"]):
                    if extra["id"] not in seen:
                        seen.add(extra["id"])
                        txs.append(extra)
            txs.sort(key=lambda t: t.get("occurred_at") or "")
            facts = bundle.get("facts") or {}
            facts["tx_ids"] = [t["id"] for t in txs]
            facts["accounts"] = sorted(
                {account_id, *[t["from_account"] for t in txs], *[t["to_account"] for t in txs]}
            )
            facts["amounts"] = sorted(set(facts.get("amounts") or []) | {t["amount"] for t in txs})
            bundle["facts"] = facts
            if "get_timeline" in planned:
                timeline = get_timeline(db, account_id, txs=txs)
            if "get_graph" in planned or "get_network" in planned:
                from .tools import get_graph

                bundle["graph"] = get_graph(db, account_id, txs=txs)
    if "search_regulation" in planned:
        search_regulation(alert["alert_type"], as_of=as_of)
    kb_ids = "、".join(h["id"] for h in kb_hits) or "（无命中）"
    bundle["facts"]["kb_ids"] = [h["id"] for h in kb_hits]

    privacy = PrivacyMap()
    privacy.build_from_bundle(bundle)

    plan = [
        f"按告警类型选择工具：{'、'.join(planned)}",
        "读取告警与上游检测来源",
        "调取客户 KYC 与开户信息",
        "抽取账户近窗交易",
        "检索制度与类型学知识库",
        "计算行业行为基线偏离" if "get_baseline" in planned else "（本类型跳过基线）",
        "查询对手方一度关联" if "get_graph" in planned else "（本类型跳过图谱）",
        "名单命中" if "check_watchlist" in planned else "（本类型跳过名单）",
        "Analyst 模式分析",
        "Challenger：规则先验 + 模型有界 delta" if use_challenger else "跳过 Challenger（消融）",
        "Validator 校验 Claim→Evidence",
        "Reporter 要素草稿 + 事实回查（脱敏进模）",
        "Human Approval（Agent 不得报送）",
    ]
    structured_plan = InvestigationPlan(
        case_id=alert["id"],
        investigation_plan=[
            PlanStep(step=i + 1, tool=t, purpose="只读取数", required=True)
            for i, t in enumerate(planned)
            if t in ALLOWED_TOOLS
        ],
    )
    steps = [
        {
            "role": "Planner",
            "title": "生成调查计划",
            "content": (
                f"告警类型「{alert['alert_type']}」。工具白名单 {len(ALLOWED_TOOLS)} 个；"
                f"本轮计划 {len(structured_plan.investigation_plan)} 步。prompt={prompt_version('planner')}。"
                "结论由规则+校验 delta，人签后才是处置。"
            ),
            "items": plan,
        }
    ]

    steps.append(
        {
            "role": "Collector",
            "title": "只读取数并留痕",
            "content": (
                f"已拉取客户 {customer['name']}（{customer['id']}）、交易 {len(txs)} 笔、"
                f"知识库 {len(kb_hits)} 条。工具调用已写入审计（见 tool_trace）。"
            ),
            "items": [
                f"KYC：{'对公' if customer['kind']=='enterprise' else '个人'} / {customer['industry']} / 开户 {customer['opened_at']}",
                f"样本流入{yuan(baseline['sample_in_sum'])}，流出{yuan(baseline['sample_out_sum'])}",
                f"关注名单命中 {len(watch_hits)} 个",
                f"知识库命中：{kb_ids}",
                f"计划工具：{'、'.join(planned)}",
            ],
        }
    )

    inflow = [t for t in txs if t["to_account"] == account_id]
    outflow = [t for t in txs if t["from_account"] == account_id]
    in_accounts = {t["from_account"] for t in inflow}
    near = [t for t in inflow if _near_threshold(t["amount"])]
    night_out = [t for t in outflow if t["occurred_at"][11:13] >= "21" or t["occurred_at"][11:13] < "06"]

    findings = []
    risk_factors: list[dict] = [
        {"code": "base-risk", "label": "起始待查分", "delta": 0.12, "evidence_ids": [], "source": "rule", "tag": None}
    ]
    score = 0.12
    in_labels = peer_labels_from_graph(bundle["graph"], account_id, txs, "in")
    out_labels = peer_labels_from_graph(bundle["graph"], account_id, txs, "out")

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

    # 未登记对手：抬高可疑但不封顶，便于落入「继续观察」
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

    base_score = score
    ev_graph = build_evidence_graph(alert["id"], bundle, kb_hits)
    allowed_evidence = sorted(
        source_ids_of(ev_graph)
        | {t["id"] for t in txs}
        | {customer["id"], alert["account_id"]}
        | {e for f in findings for e in f.get("evidence_ids", [])}
    )
    claims = [
        {
            "claim": f["title"],
            "evidence_ids": f.get("evidence_ids") or [],
            "tag": f.get("code"),
            "polarity": "counter" if f.get("code") in {"pattern-peer", "thin"} else "support",
        }
        for f in findings
    ]

    challenger: list[dict] = []
    challenger_usage: dict = {}
    rule_prior = 0.0
    llm_delta = 0.0
    rejected_claims: list[dict] = []

    if use_challenger:
        rule_prior, score_hints = _rule_prior(
            use_challenger=True,
            customer=customer,
            in_labels=in_labels,
            out_labels=out_labels,
            baseline=baseline,
            kb_hits=kb_hits,
            txs=txs,
        )
        if rule_prior:
            risk_factors.append(
                {
                    "code": "challenger-prior",
                    "label": "质疑规则先验",
                    "delta": rule_prior,
                    "evidence_ids": [customer["id"]],
                    "source": "rule",
                    "tag": None,
                }
            )
        try:
            raw_ch, raw_delta, challenger_usage = enrich_challenger(
                db=db,
                privacy=privacy,
                alert=alert,
                customer=customer,
                findings=findings,
                baseline=baseline,
                kb_hits=kb_hits,
                score_hints=score_hints,
                allowed_evidence=allowed_evidence,
            )
        except RuntimeError as e:
            warning(f"Challenger 失败，仅保留规则先验: {e}")
            raw_ch, raw_delta = [], 0.0
        evidence_case = {eid: alert["id"] for eid in allowed_evidence}
        challenger, llm_delta, rejected_claims = filter_challenger_items(
            raw_ch,
            allowed=set(allowed_evidence),
            case_id=alert["id"],
            evidence_case=evidence_case,
        )
        for i, c in enumerate(challenger, start=1):
            ev_graph.append(
                {
                    "evidence_id": f"EV-C{i:03d}",
                    "case_id": alert["id"],
                    "evidence_type": "COUNTER_EVIDENCE",
                    "source_type": "challenger",
                    "source_id": (c.get("evidence_ids") or [""])[0],
                    "description": c.get("claim") or c.get("title") or "",
                    "raw_reference": ",".join(c.get("evidence_ids") or []),
                    "timestamp": "",
                    "reliability": 0.7,
                    "created_by": "challenger",
                    "polarity": "counter",
                    "metadata": {"delta": c.get("delta")},
                    "data_note": "synthetic",
                }
            )
        if abs(llm_delta) > 0:
            risk_factors.append(
                {
                    "code": "challenger-llm",
                    "label": "校验后模型 delta",
                    "delta": llm_delta,
                    "evidence_ids": [i for c in challenger for i in (c.get("evidence_ids") or [])],
                    "source": "challenger",
                    "tag": None,
                }
            )
        score = base_score + rule_prior + llm_delta
        steps.append(
            {
                "role": "Challenger",
                "title": "规则先验 + 有界调分（Validator 后）",
                "content": (
                    f"规则先验 {rule_prior:+.2f}；校验后 delta {llm_delta:+.2f}（±0.15，"
                    f"无证据/越界已拒绝 {len(rejected_claims)} 条）。prompt={prompt_version('challenger')}。"
                ),
                "items": [
                    f"{c.get('claim') or c['title']}（delta={c.get('delta', 0):+.2f}，证据 {','.join(c.get('evidence_ids') or []) or '无'}）：{c.get('detail') or ''}"
                    for c in challenger
                ],
            }
        )
        steps.append(
            {
                "role": "Validator",
                "title": "Evidence Validator",
                "content": f"允许证据 {len(allowed_evidence)} 个；拒绝 {len(rejected_claims)} 条 Claim。失败项不得进分。",
                "items": [r.get("validation", {}).get("reason") or "ok" for r in rejected_claims] or ["本轮 Claim 均通过编号校验"],
            }
        )
    else:
        steps.append(
            {
                "role": "Challenger",
                "title": "本轮已关闭（消融）",
                "content": "未执行规则先验与模型调分，用于对比误上报是否上升。",
                "items": ["未执行反证，置信度未下调。"],
            }
        )

    risk = aggregate(risk_factors, challenger_delta=0.0)
    # 因子已含先验与校验 delta，不再重复加
    score = max(0.05, min(0.95, score))
    conclusion = _score_to_conclusion(score)
    risk["final"] = round(score, 4)
    risk["conclusion"] = conclusion
    risk["recommendation"] = CONCLUSION_TO_RECO[conclusion]
    risk["recommendation_label"] = RECO_LABEL[risk["recommendation"]]
    risk["risk_level"] = score_to_level(score)

    drop = next((f["code"] for f in risk_factors if f.get("delta", 0) > 0.2), "upstream-alert")
    cf = counterfactual(risk_factors, [drop], challenger_delta=0.0)

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
        alert, customer, baseline, findings, challenger, conclusion, txs, inflow, outflow, use_challenger, kb_hits
    )
    sample_ids = report["sample_ids"]
    fact_retry = False
    reporter_usage: dict = {}

    def _apply_reason(polished: str) -> None:
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

    polished, reporter_usage = enrich_report_reason(
        db=db,
        privacy=privacy,
        alert=alert,
        customer=customer,
        conclusion_label=CONCLUSION_LABEL[conclusion],
        findings=findings,
        challenger=challenger,
        kb_hits=kb_hits,
        sample_ids=sample_ids,
        draft_reason=report["reason"],
    )
    _apply_reason(polished)
    reason_issues = fact_check(report["reason"], bundle["facts"])
    if reason_issues:
        fact_retry = True
        polished, reporter_usage = enrich_report_reason(
            db=db,
            privacy=privacy,
            alert=alert,
            customer=customer,
            conclusion_label=CONCLUSION_LABEL[conclusion],
            findings=findings,
            challenger=challenger,
            kb_hits=kb_hits,
            sample_ids=sample_ids,
            draft_reason=report["reason"],
            prior_issues=reason_issues,
        )
        _apply_reason(polished)

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
            "content": f"理由由百炼 {llm_model()} 生成（脱敏进模）；事实不匹配不可签发。",
            "items": [
                f"建议结论：{CONCLUSION_LABEL[conclusion]}（置信度 {int(score * 100)}%）",
                f"打分：底分 {base_score:.2f} + 规则先验 {rule_prior:+.2f} + 模型delta {llm_delta:+.2f}",
                f"事实回查问题数：{len(issues)}" + ("（已自动重写一次）" if fact_retry else ""),
                f"知识库引用：{kb_ids}",
                f"工具调用次数：{len(tool_trace)}",
                "Agent 不可自动报送，须调查员签发。",
            ],
        }
    )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    elements_ok = sum(1 for e in report["elements"] if (e.get("value") or "").strip())
    payload = {
        "alert": alert,
        "customer": customer,
        "plan": plan,
        "steps": steps,
        "tool_trace": tool_trace,
        "findings": findings,
        "challenger": challenger,
        "use_challenger": use_challenger,
        "inject_hallucination": inject_hallucination,
        "scoring": {
            "base": round(base_score, 4),
            "rule_prior": rule_prior,
            "llm_delta": llm_delta,
            "final": round(score, 4),
        },
        "llm": {
            "challenger": use_challenger,
            "reporter": True,
            "provider": "阿里云百炼 / DashScope",
            "model": llm_model(),
            "masked": True,
            "fact_retry": fact_retry,
            "usage": {"challenger": challenger_usage if use_challenger else None, "reporter": reporter_usage},
        },
        "privacy": {"masked_names": len(privacy.name_to_mask), "masked_accounts": len(privacy.acct_to_mask)},
        "conclusion": conclusion,
        "conclusion_label": CONCLUSION_LABEL[conclusion],
        "confidence": round(score, 2),
        "report": report,
        "evidence": evidence,
        "evidence_graph": ev_graph,
        "claims": claims,
        "rejected_claims": rejected_claims,
        "timeline": timeline,
        "risk": risk,
        "counterfactual": cf,
        "investigation_plan": structured_plan.model_dump(),
        "prompt_versions": {
            "planner": prompt_version("planner"),
            "challenger": prompt_version("challenger"),
            "reporter": prompt_version("reporter"),
            "validator": prompt_version("validator"),
        },
        "data_note": "synthetic",
        "case_v2": {
            "case_id": alert["id"],
            "status": "INVESTIGATING",
            "risk_level": risk["risk_level"],
            "recommendation": risk["recommendation"],
            "recommendation_label": risk["recommendation_label"],
            "suspicious_types": tags_from_findings(findings),
            "human_required": True,
            "data_note": "synthetic",
        },
        "structured_report": StructuredReport(
            case_overview=f"{alert['title']} / {alert['id']}",
            customer_profile=customer.get("summary") or customer["name"],
            transaction_summary=f"流入{len(inflow)} 流出{len(outflow)}",
            suspicious_patterns=[f["title"] for f in findings],
            evidence_ids=[e["id"] for e in evidence[:20]],
            counter_evidence_ids=[c.get("evidence_ids", [None])[0] for c in challenger if c.get("evidence_ids")][:8],
            network_analysis=f"节点 {len((bundle.get('graph') or {}).get('nodes') or [])}",
            risk_assessment=risk["recommendation_label"],
            challenger_review="；".join((c.get("claim") or "") for c in challenger) or "未启用",
            regulation_basis=[
                RegulationCite(
                    regulation_id=h["id"],
                    title=h.get("title") or "",
                    article=h.get("article") or "",
                    evidence=h.get("snippet") or "",
                    source=h.get("source") or "",
                    as_of=as_of,
                )
                for h in kb_hits
                if h.get("kind") == "regulation"
            ]
            or [
                RegulationCite(
                    regulation_id="",
                    title="未检索到足够法规依据",
                    evidence="禁止编造条款",
                    source="",
                    as_of=as_of,
                )
            ],
            recommendation=risk["recommendation"],
        ).model_dump(),
        "graph": bundle["graph"],
        "baseline": baseline,
        "watch_hits": watch_hits,
        "kb_hits": kb_hits,
        "transactions": txs,
        "fact_issues": issues,
        "can_sign": len(issues) == 0,
        "elapsed_ms": elapsed_ms,
        "comparison": {
            "agent_ms": elapsed_ms,
            "tools_called": len(tool_trace),
            "elements_filled": elements_ok,
            "elements_total": len(report["elements"]),
            "evidence_linkable": True,
            "note": "对比项均为当场可验证指标（工具次数/要素非空/证据可回溯），不再使用拍脑袋人工分钟数。",
        },
    }
    try:
        persist_investigation(db, payload)
        audit(f"case persisted {alert['id']}")
    except Exception as e:
        warning(f"case persist skipped: {e}")
    return payload


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
