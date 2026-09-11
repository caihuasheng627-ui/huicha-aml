from __future__ import annotations

import time

from sqlalchemy.orm import Session

from .analyst_rules import CONCLUSION_LABEL, analyze, rule_prior, score_to_conclusion
from .case_store import persist_investigation
from .evidence import build_evidence_graph, source_ids_of
from .knowledge import retrieve_for_alert
from .llm import enrich_challenger, enrich_report_reason, llm_model
from .logging_util import audit, warning
from .privacy import PrivacyMap
from .prompts import prompt_version
from .report_draft import apply_reason, render_report
from .risk import CONCLUSION_TO_RECO, RECO_LABEL, aggregate, counterfactual, score_to_level
from .schema import InvestigationPlan, PlanStep, RegulationCite, StructuredReport
from .tool_audit import bind_tool_context, reset_tool_context, tool
from .tools import (
    ALLOWED_TOOLS,
    collect_bundle,
    fact_check,
    get_accounts,
    get_graph,
    get_related_accounts,
    get_timeline,
    get_transactions,
    plan_tool_names,
    search_regulation,
    yuan,
)
from .typology import tags_from_findings
from .validator import filter_challenger_items

FAKE_ACCOUNT = "6222-FAKE-9999"


@tool("search_knowledge")
def search_knowledge_tool(alert_type: str, industry: str, as_of: str = "") -> list[dict]:
    return retrieve_for_alert(alert_type, industry, as_of=as_of)


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


def _collect_stage(db: Session, alert_id: str) -> dict:
    bundle = collect_bundle(db, alert_id)
    alert = bundle["alert"]
    customer = bundle["customer"]
    planned = bundle.get("planned_tools") or plan_tool_names(alert["alert_type"])
    as_of = (alert.get("created_at") or "")[:10]
    txs = bundle["transactions"]
    account_id = alert["account_id"]
    kb_hits = search_knowledge_tool(alert["alert_type"], customer["industry"], as_of)
    if "get_accounts" in planned:
        get_accounts(db, customer["id"])
    timeline = get_timeline(db, account_id, txs=txs) if "get_timeline" in planned else []
    if "get_related_accounts" in planned:
        peers = get_related_accounts(db, account_id, txs=txs)
        if len(peers) <= 4:
            seen = {t["id"] for t in txs}
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
                bundle["graph"] = get_graph(db, account_id, txs=txs)
    if "search_regulation" in planned:
        search_regulation(alert["alert_type"], as_of=as_of)
    bundle["facts"]["kb_ids"] = [h["id"] for h in kb_hits]
    return {
        "bundle": bundle,
        "alert": alert,
        "customer": customer,
        "planned": planned,
        "as_of": as_of,
        "txs": txs,
        "kb_hits": kb_hits,
        "timeline": timeline,
        "account_id": account_id,
    }


def _challenger_stage(
    *,
    db: Session,
    privacy: PrivacyMap,
    alert: dict,
    customer: dict,
    findings: list[dict],
    baseline: dict,
    kb_hits: list[dict],
    txs: list[dict],
    in_labels: list[str],
    out_labels: list[str],
    allowed_evidence: list[str],
    risk_factors: list[dict],
    use_challenger: bool,
) -> dict:
    if not use_challenger:
        return {"challenger": [], "usage": {}, "rule_prior": 0.0, "llm_delta": 0.0, "rejected": [], "hints": []}
    prior, hints = rule_prior(
        use_challenger=True,
        customer=customer,
        in_labels=in_labels,
        out_labels=out_labels,
        baseline=baseline,
        kb_hits=kb_hits,
        txs=txs,
    )
    if prior:
        risk_factors.append(
            {
                "code": "challenger-prior",
                "label": "质疑规则先验",
                "delta": prior,
                "evidence_ids": [customer["id"]],
                "source": "rule",
                "tag": None,
            }
        )
    try:
        raw_ch, _raw_delta, usage = enrich_challenger(
            db=db,
            privacy=privacy,
            alert=alert,
            customer=customer,
            findings=findings,
            baseline=baseline,
            kb_hits=kb_hits,
            score_hints=hints,
            allowed_evidence=allowed_evidence,
        )
    except RuntimeError as e:
        warning(f"Challenger 失败，仅保留规则先验: {e}")
        raw_ch, usage = [], {}
    evidence_case = {eid: alert["id"] for eid in allowed_evidence}
    challenger, llm_delta, rejected = filter_challenger_items(
        raw_ch,
        allowed=set(allowed_evidence),
        case_id=alert["id"],
        evidence_case=evidence_case,
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
    return {
        "challenger": challenger,
        "usage": usage,
        "rule_prior": prior,
        "llm_delta": llm_delta,
        "rejected": rejected,
        "hints": hints,
    }


def _run_investigation_inner(
    db: Session,
    alert_id: str,
    *,
    use_challenger: bool,
    inject_hallucination: bool,
    started: float,
    tool_trace: list,
) -> dict:
    collected = _collect_stage(db, alert_id)
    bundle = collected["bundle"]
    alert = collected["alert"]
    customer = collected["customer"]
    planned = collected["planned"]
    as_of = collected["as_of"]
    txs = collected["txs"]
    kb_hits = collected["kb_hits"]
    timeline = collected["timeline"]
    account_id = collected["account_id"]
    baseline = bundle["baseline"]
    watch_hits = bundle["watch_hits"]
    kb_ids = "、".join(h["id"] for h in kb_hits) or "（无命中）"

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
        },
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
        },
    ]

    analyst = analyze(
        alert=alert,
        customer=customer,
        txs=txs,
        account_id=account_id,
        baseline=baseline,
        watch_hits=watch_hits,
        graph=bundle["graph"],
    )
    findings = analyst["findings"]
    risk_factors = analyst["risk_factors"]
    score = analyst["score"]
    inflow, outflow = analyst["inflow"], analyst["outflow"]
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

    ch = _challenger_stage(
        db=db,
        privacy=privacy,
        alert=alert,
        customer=customer,
        findings=findings,
        baseline=baseline,
        kb_hits=kb_hits,
        txs=txs,
        in_labels=analyst["in_labels"],
        out_labels=analyst["out_labels"],
        allowed_evidence=allowed_evidence,
        risk_factors=risk_factors,
        use_challenger=use_challenger,
    )
    challenger = ch["challenger"]
    llm_delta = ch["llm_delta"]
    rule_prior_v = ch["rule_prior"]
    rejected_claims = ch["rejected"]
    challenger_usage = ch["usage"]

    if use_challenger:
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
        score = base_score + rule_prior_v + llm_delta
        steps.append(
            {
                "role": "Challenger",
                "title": "规则先验 + 有界调分（Validator 后）",
                "content": (
                    f"规则先验 {rule_prior_v:+.2f}；校验后 delta {llm_delta:+.2f}（±0.15，"
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
                "content": (
                    f"允许证据 {len(allowed_evidence)} 个；拒绝 {len(rejected_claims)} 条 Claim。"
                    "support_score 仅表示编号是否属于本案，不是语义置信度。"
                ),
                "items": [r.get("validation", {}).get("reason") or "ok" for r in rejected_claims]
                or ["本轮 Claim 均通过编号校验"],
            }
        )
    else:
        steps.append(
            {
                "role": "Challenger",
                "title": "本轮已关闭（消融）",
                "content": "未执行规则先验与模型调分，用于对比误上报是否上升。",
                "items": ["未执行反证，规则分未下调。"],
            }
        )

    risk = aggregate(risk_factors, challenger_delta=0.0)
    score = max(0.05, min(0.95, score))
    conclusion = score_to_conclusion(score)
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

    report = render_report(
        alert, customer, baseline, findings, challenger, conclusion, txs, inflow, outflow, use_challenger, kb_hits
    )
    fact_retry = False
    polished, reporter_usage = enrich_report_reason(
        db=db,
        privacy=privacy,
        alert=alert,
        customer=customer,
        conclusion_label=CONCLUSION_LABEL[conclusion],
        findings=findings,
        challenger=challenger,
        kb_hits=kb_hits,
        sample_ids=report["sample_ids"],
        draft_reason=report["reason"],
    )
    apply_reason(report, polished, conclusion)
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
            sample_ids=report["sample_ids"],
            draft_reason=report["reason"],
            prior_issues=reason_issues,
        )
        apply_reason(report, polished, conclusion)

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
                f"建议结论：{CONCLUSION_LABEL[conclusion]}（规则分 {score:.2f}，非校准准确率）",
                f"打分：底分 {base_score:.2f} + 规则先验 {rule_prior_v:+.2f} + 模型delta {llm_delta:+.2f}",
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
            "rule_prior": rule_prior_v,
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
        "confidence_kind": "rule_score_not_calibrated",
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
