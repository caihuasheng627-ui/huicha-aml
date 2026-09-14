from __future__ import annotations

import time

from sqlalchemy.orm import Session

from .analyst_rules import CONCLUSION_LABEL, analyze
from .case_store import persist_investigation
from .checklist import attach_checklist, enrich_counterparties
from .decision import apply_guardrails, decision_claims, normalize_judge, rule_baseline, verify_judge
from .evidence import build_evidence_graph, source_ids_of
from .knowledge import retrieve_for_alert
from .llm import enrich_full_report, enrich_judge, llm_model
from .logging_util import audit, warning
from .privacy import PrivacyMap
from .prompts import prompt_version
from .report_draft import apply_full_text, render_report
from .risk import CONCLUSION_TO_RECO, RECO_LABEL
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

FAKE_ACCOUNT = "6222-FAKE-9999"


@tool("search_knowledge")
def search_knowledge_tool(alert_type: str, industry: str, as_of: str = "") -> list[dict]:
    return retrieve_for_alert(alert_type, industry, as_of=as_of)


def regulation_cites(kb_hits: list[dict], as_of: str) -> list[RegulationCite]:
    """法规依据须带转述正文与版本信息，前端展开即可核对；未命中也要留痕。"""
    cites = [
        RegulationCite(
            regulation_id=h["id"],
            title=h.get("title") or "",
            article=h.get("article") or "",
            evidence=h.get("snippet") or "",
            source=h.get("source") or "",
            as_of=as_of,
            effective_date=h.get("effective_date") or "",
            kind_label=h.get("kind_label") or "",
        )
        for h in kb_hits
        if h.get("kind") == "regulation"
    ]
    return cites or [
        RegulationCite(
            regulation_id="",
            title="未检索到足够法规依据",
            evidence="禁止编造条款",
            source="",
            as_of=as_of,
        )
    ]


def run_investigation(
    db: Session,
    alert_id: str,
    *,
    use_challenger: bool = True,
    inject_hallucination: bool = False,
    experiment_mode: bool = False,
) -> dict:
    started = time.perf_counter()
    tool_trace: list = []
    tokens = bind_tool_context(db=db, alert_id=alert_id, trace=tool_trace)
    try:
        return _run_investigation_v3(
            db,
            alert_id,
            use_challenger=use_challenger,
            inject_hallucination=inject_hallucination,
            experiment_mode=experiment_mode,
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
            facts["dates"] = sorted(set(facts.get("dates") or []) | {(t.get("occurred_at") or "")[:10] for t in txs})
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


def _run_investigation_v3(
    db: Session,
    alert_id: str,
    *,
    use_challenger: bool,
    inject_hallucination: bool,
    experiment_mode: bool,
    started: float,
    tool_trace: list,
) -> dict:
    """V3：AI 给完整调查建议；规则仅作指标、对照和硬护栏。"""
    collected = _collect_stage(db, alert_id)
    bundle = collected["bundle"]
    alert = collected["alert"]
    customer = collected["customer"]
    txs = collected["txs"]
    kb_hits = collected["kb_hits"]
    baseline = bundle["baseline"]
    watch_hits = bundle["watch_hits"]
    planned = collected["planned"]
    as_of = collected["as_of"]
    account_id = collected["account_id"]
    privacy = PrivacyMap()
    privacy.build_from_bundle(bundle)

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
    baseline_result = rule_baseline(analyst)
    ev_graph = build_evidence_graph(alert["id"], bundle, kb_hits)
    allowed_evidence = sorted(
        source_ids_of(ev_graph)
        | {t["id"] for t in txs}
        | {customer["id"], alert["account_id"]}
        | {e for f in findings for e in f.get("evidence_ids", [])}
    )
    # 报告回查时，告警号与证据号是本案已知引用，不应被拆成数字片段误报。
    bundle["facts"]["ref_ids"] = sorted(set(bundle["facts"].get("ref_ids") or []) | {alert["id"]} | set(allowed_evidence))

    judge_usage: dict = {}
    judge_repaired = False
    fallback_reason = ""
    allowed_set = set(allowed_evidence)

    def _judge_once(prior_issues: list[dict] | None) -> tuple[dict, dict, dict]:
        raw, usage = enrich_judge(
            db=db,
            privacy=privacy,
            alert=alert,
            customer=customer,
            findings=findings,
            transactions=txs,
            baseline=baseline,
            kb_hits=kb_hits,
            allowed_evidence=allowed_evidence,
            prior_issues=prior_issues,
        )
        decision = normalize_judge(raw, known_ids=allowed_set)
        return decision, verify_judge(decision, allowed_evidence=allowed_set), usage

    if use_challenger:
        try:
            try:
                judge, judge_validation, judge_usage = _judge_once(None)
                repair_issues = judge_validation["issues"] if not judge_validation["passed"] else []
            except (RuntimeError, ValueError) as exc:
                # 截断/非 JSON/字段非法都给一次带针对性提示的修复机会，而不是直接降级。
                judge = None
                repair_issues = [{"kind": "invalid_output", "message": str(exc)[:300]}]
            if repair_issues:
                judge_repaired = True
                judge, judge_validation, judge_usage = _judge_once(repair_issues)
        except (RuntimeError, ValueError) as exc:
            fallback_reason = str(exc)
            judge = {
                "disposition": baseline_result["conclusion"],
                "confidence": baseline_result["score"],
                "typologies": tags_from_findings(findings),
                "supporting_evidence_ids": [
                    e for f in findings if f.get("polarity") == "support" for e in f.get("evidence_ids", [])
                ][:8],
                "contradicting_evidence_ids": [
                    e for f in findings if f.get("polarity") == "counter" for e in f.get("evidence_ids", [])
                ][:8],
                "missing_evidence": ["AI Judge 调用失败，须人工完整复核"],
                "rationale": [],
                "next_actions": ["人工复核规则对照与原始证据"],
            }
            judge_validation = {
                "passed": False,
                "issues": [{"kind": "judge_failure", "message": fallback_reason}],
                "citation_count": 0,
                "invalid_ids": [],
                "score_kind": "fallback",
                "reason": "AI Judge 失败，已降级为规则对照",
            }
    else:
        judge = {
            "disposition": baseline_result["conclusion"],
            "confidence": baseline_result["score"],
            "typologies": tags_from_findings(findings),
            "supporting_evidence_ids": [
                e for f in findings if f.get("polarity") == "support" for e in f.get("evidence_ids", [])
            ][:8],
            "contradicting_evidence_ids": [
                e for f in findings if f.get("polarity") == "counter" for e in f.get("evidence_ids", [])
            ][:8],
            "missing_evidence": ["AI Judge 已关闭，当前仅展示规则对照"],
            "rationale": [],
            "next_actions": ["启用 AI Judge 或由调查员人工研判"],
        }
        judge_validation = {
            "passed": True,
            "issues": [],
            "citation_count": 0,
            "invalid_ids": [],
            "score_kind": "rule_only_ablation",
            "reason": "实验模式：AI Judge 已关闭",
        }

    guardrails = apply_guardrails(judge, watch_hits=watch_hits)
    conclusion = guardrails["final_conclusion"]
    confidence = float(judge.get("confidence") or 0)
    confidence = max(0.0, min(1.0, confidence))

    # 对 Judge 声称的关键支持证据做一次最小剔除，观察建议是否连贯变化。
    counterfactual_result = {
        "performed": False,
        "faithful": None,
        "removed_evidence_ids": [],
        "original_conclusion": judge["disposition"],
        "counterfactual_conclusion": "",
        "note": "无可剔除的关键支持证据，未执行 AI 反事实。",
    }
    if use_challenger and judge_validation["passed"] and judge.get("supporting_evidence_ids"):
        key_id = judge["supporting_evidence_ids"][0]
        key_finding = next(
            (f for f in findings if key_id in (f.get("evidence_ids") or []) and f.get("polarity") == "support"),
            None,
        )
        removed_ids = set((key_finding or {}).get("evidence_ids") or [key_id])
        cf_allowed = allowed_set - removed_ids
        # 其余指标里也可能引用被移除的流水；不擦掉的话模型会照抄，导致反事实轮次因「伪造引用」失效。
        cf_findings = []
        for f in findings:
            if f is key_finding:
                continue
            kept_ids = [e for e in (f.get("evidence_ids") or []) if e not in removed_ids]
            if f.get("evidence_ids") and not kept_ids and f.get("polarity") != "context":
                continue
            cf_findings.append({**f, "evidence_ids": kept_ids})
        try:
            raw_cf, _ = enrich_judge(
                db=db,
                privacy=privacy,
                alert=alert,
                customer=customer,
                findings=cf_findings,
                transactions=[t for t in txs if t.get("id") not in removed_ids],
                baseline=baseline,
                kb_hits=kb_hits,
                allowed_evidence=[e for e in allowed_evidence if e not in removed_ids],
                prior_issues=[
                    {
                        "kind": "counterfactual",
                        "message": f"移除指标「{(key_finding or {}).get('title') or key_id}」及其证据后重新判断",
                    }
                ],
            )
            cf_judge = normalize_judge(raw_cf, known_ids=cf_allowed)
            cf_valid = verify_judge(cf_judge, allowed_evidence=cf_allowed)
            changed = cf_judge["disposition"] != judge["disposition"]
            if not cf_valid["passed"]:
                note = "反事实轮次输出未通过引用校验，无法判断建议是否依赖该证据，已标记供人工复核"
                faithful = None
            elif changed:
                note = "移除模型声明的关键证据后建议随之变化"
                faithful = True
            else:
                note = "移除关键证据后建议未变化，已标记供人工复核"
                faithful = False
            counterfactual_result = {
                "performed": True,
                "faithful": faithful,
                "validated": cf_valid["passed"],
                "validation_issues": cf_valid["issues"],
                "removed_evidence_ids": sorted(removed_ids),
                "original_conclusion": judge["disposition"],
                "counterfactual_conclusion": cf_judge["disposition"],
                "note": note,
            }
        except (RuntimeError, ValueError) as exc:
            counterfactual_result["note"] = f"反事实执行失败：{exc}"

    report = render_report(
        alert,
        customer,
        baseline,
        findings,
        [],
        conclusion,
        txs,
        analyst["inflow"],
        analyst["outflow"],
        use_challenger,
        kb_hits,
    )
    reporter_usage: dict = {}
    fact_retry = False
    if use_challenger and judge_validation["passed"]:
        report_context = {
            "conclusion": conclusion,
            "conclusion_label": CONCLUSION_LABEL[conclusion],
            "customer": {k: customer.get(k) for k in ("id", "name", "industry", "opened_at")},
            "alert": {k: alert.get(k) for k in ("id", "alert_type", "account_id", "created_at")},
            "judge": {k: v for k, v in judge.items() if k != "sanitized_missing_evidence"},
            "findings": findings,
            "evidence_ids": list(
                dict.fromkeys(
                    [
                        *(judge.get("supporting_evidence_ids") or []),
                        *(judge.get("contradicting_evidence_ids") or []),
                    ]
                )
            )[:12],
            "regulation_ids": [h["id"] for h in kb_hits if h.get("kind") == "regulation"],
            "template": report["full_text"],
        }
        try:
            full_text, reporter_usage = enrich_full_report(
                db=db, privacy=privacy, context=report_context
            )
            apply_full_text(report, full_text, conclusion)
            report_issues = fact_check(report["full_text"], bundle["facts"])
            if report_issues:
                fact_retry = True
                full_text, reporter_usage = enrich_full_report(
                    db=db,
                    privacy=privacy,
                    context=report_context,
                    prior_issues=report_issues,
                )
                apply_full_text(report, full_text, conclusion)
        except RuntimeError as exc:
            warning(f"Reporter 全文生成失败，使用确定性模板: {exc}")

    if inject_hallucination:
        poison = f"另发现未在工具结果中出现的对手账户 {FAKE_ACCOUNT}。"
        report["reason"] += poison
        report["full_text"] += "\n【注入幻觉演示】" + poison
    fact_issues = fact_check(report["full_text"], bundle["facts"])
    guardrails = apply_guardrails(judge, watch_hits=watch_hits, fact_issues=fact_issues)
    conclusion = guardrails["final_conclusion"]

    for i, row in enumerate(judge.get("rationale") or [], start=1):
        ev_graph.append(
            {
                "evidence_id": f"EV-{alert['id']}-J{i:03d}",
                "case_id": alert["id"],
                "evidence_type": "MODEL",
                "source_type": "judge",
                "source_id": (row.get("evidence_ids") or [""])[0],
                "description": row.get("text") or "",
                "raw_reference": ",".join(row.get("evidence_ids") or []),
                "timestamp": "",
                "reliability": confidence,
                "created_by": "judge",
                "polarity": "support",
                "metadata": {"confidence_kind": "llm_self_assessed_not_calibrated"},
                "data_note": "synthetic",
            }
        )

    plan = [
        f"按告警类型选择只读工具：{'、'.join(planned)}",
        "从流水、KYC、图谱和知识库提取支持/反向/缺失证据",
        "AI Judge 输出完整三档建议与逐条引用",
        "Skeptic 校验证据契约并执行一次关键证据反事实",
        "政策护栏只作否决或升级，不参与加权",
        "Reporter 生成四段全文并做事实回查",
        "Human Approval（Agent 不得报送）",
    ]
    steps = [
        {
            "role": "Planner",
            "title": "生成只读调查计划",
            "content": f"本轮计划 {len(planned)} 个白名单工具；上游告警只决定取数范围，不进入结论加分。",
            "items": plan,
        },
        {
            "role": "Collector",
            "title": "证据归集",
            "content": f"已调取 {len(txs)} 笔交易、{len(kb_hits)} 条知识、{len(tool_trace)} 次工具调用。",
            "items": [f"工具：{name}" for name in planned],
        },
        {
            "role": "Analyst",
            "title": "事实指标与规则对照",
            "content": f"提取 {len(findings)} 项事实指标；规则对照为{CONCLUSION_LABEL[baseline_result['conclusion']]}，不决定最终建议。",
            "items": [f"{f['title']}：{f['detail']}" for f in findings],
        },
        {
            "role": "Judge",
            "title": "证据约束的 AI 调查建议",
            "content": f"AI 建议{CONCLUSION_LABEL[judge['disposition']]}；自评把握度 {confidence:.2f}（未校准）。",
            "items": [f"{r['text']}（证据 {','.join(r.get('evidence_ids') or [])}）" for r in judge.get("rationale") or []],
        },
        {
            "role": "Skeptic",
            "title": "引用校验与反事实检查",
            "content": judge_validation["reason"],
            "items": [
                *(i.get("message") or str(i) for i in judge_validation.get("issues") or []),
                counterfactual_result["note"],
            ],
        },
        {
            "role": "PolicyGuardrail",
            "title": "政策硬护栏",
            "content": guardrails["note"],
            "items": [f"{c['label']}：{c['effect']}" for c in guardrails["checks"]],
        },
        {
            "role": "Reporter",
            "title": "四段全文草稿 + 事实回查",
            "content": f"全文由 Reporter 生成并回查；发现 {len(fact_issues)} 个事实问题。",
            "items": ["Agent 不可自动报送，须调查员签发。"],
        },
    ]
    risk_level = {"exclude": "LOW", "observe": "MEDIUM", "suggest_report": "HIGH"}[conclusion]
    recommendation = CONCLUSION_TO_RECO[conclusion]
    risk = {
        "factors": baseline_result["factors"],
        "rule_baseline": baseline_result,
        "judge": judge,
        "guardrails": guardrails,
        "final": confidence,
        "conclusion": conclusion,
        "recommendation": recommendation,
        "recommendation_label": RECO_LABEL[recommendation],
        "risk_level": risk_level,
        "note": "最终建议来自通过证据契约的 AI Judge；规则分仅作对照，护栏仅作政策边界。",
    }
    evidence = [
        {
            "id": t["id"],
            "type": "transaction",
            "from_account": t["from_account"],
            "to_account": t["to_account"],
            "amount": t["amount"],
            "occurred_at": t["occurred_at"],
            "channel": t["channel"],
            "remark": t["remark"],
            "summary": f"{t['occurred_at']} {t['from_account']} → {t['to_account']} {yuan(t['amount']).strip()}",
        }
        for t in txs
    ]
    evidence.append(
        {
            "id": customer["id"],
            "type": "kyc",
            "summary": f"{customer['name']}，{customer['industry']}，开户 {customer['opened_at']}",
        }
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    payload = {
        "alert": alert,
        "customer": customer,
        "plan": plan,
        "steps": steps,
        "tool_trace": tool_trace,
        "findings": findings,
        "judge": judge,
        "judge_validation": judge_validation,
        "judge_repaired": judge_repaired,
        "judge_fallback_reason": fallback_reason,
        "rule_baseline": baseline_result,
        "policy_guardrails": guardrails,
        "counterfactual": counterfactual_result,
        "use_challenger": use_challenger,
        "case_challenger_enabled": use_challenger,
        "experiment_mode": experiment_mode,
        "challenger": [],
        "challenger_run": {
            "enabled": use_challenger,
            "ablation": not use_challenger,
            "label": "AI Judge",
            "initial_score": baseline_result["score"],
            "initial_conclusion": baseline_result["conclusion"],
            "initial_label": CONCLUSION_LABEL[baseline_result["conclusion"]],
            "final_score": confidence,
            "final_conclusion": conclusion,
            "final_label": CONCLUSION_LABEL[conclusion],
            "claims": decision_claims(judge),
            "validator": judge_validation,
        },
        "validator_result": judge_validation,
        "scoring": {
            "base": baseline_result["score"],
            "rule_prior": 0.0,
            "llm_delta": 0.0,
            "raw": confidence,
            "final": confidence,
            "mode": "judge_not_additive",
            "note": "规则对照与 AI 自评把握度不相加。",
        },
        "llm": {
            "judge": use_challenger,
            "reporter": use_challenger,
            "provider": "阿里云百炼 / DashScope",
            "model": llm_model(),
            "masked": True,
            "fact_retry": fact_retry,
            "usage": {"judge": judge_usage, "reporter": reporter_usage},
        },
        "privacy": {"masked_names": len(privacy.name_to_mask), "masked_accounts": len(privacy.acct_to_mask)},
        "conclusion": conclusion,
        "conclusion_label": CONCLUSION_LABEL[conclusion],
        "confidence": round(confidence, 2),
        "confidence_kind": "llm_self_assessed_not_calibrated" if use_challenger else "rule_score_not_calibrated",
        "report": report,
        "evidence": evidence,
        "evidence_graph": ev_graph,
        "claims": decision_claims(judge),
        "rejected_claims": judge_validation.get("issues") or [],
        "timeline": collected["timeline"],
        "risk": risk,
        "investigation_plan": InvestigationPlan(
            case_id=alert["id"],
            investigation_plan=[
                PlanStep(step=i + 1, tool=name, purpose="只读取数", required=True)
                for i, name in enumerate(planned)
                if name in ALLOWED_TOOLS
            ],
        ).model_dump(),
        "prompt_versions": {
            "planner": prompt_version("planner"),
            "judge": prompt_version("judge"),
            "skeptic": prompt_version("skeptic"),
            "reporter": prompt_version("reporter"),
        },
        "data_note": "synthetic",
        "case_v2": {
            "case_id": alert["id"],
            "status": "INVESTIGATING",
            "risk_level": risk_level,
            "recommendation": recommendation,
            "recommendation_label": RECO_LABEL[recommendation],
            "suspicious_types": tags_from_findings(findings),
            "human_required": True,
            "data_note": "synthetic",
        },
        "structured_report": StructuredReport(
            case_overview=f"{alert['title']} / {alert['id']}",
            customer_profile=customer.get("summary") or customer["name"],
            transaction_summary=f"流入{len(analyst['inflow'])} 流出{len(analyst['outflow'])}",
            suspicious_patterns=[f["title"] for f in findings],
            evidence_ids=judge.get("supporting_evidence_ids") or [],
            counter_evidence_ids=judge.get("contradicting_evidence_ids") or [],
            network_analysis=f"节点 {len((bundle.get('graph') or {}).get('nodes') or [])}",
            risk_assessment=RECO_LABEL[recommendation],
            challenger_review="；".join(r.get("text") or "" for r in judge.get("rationale") or []),
            regulation_basis=regulation_cites(kb_hits, as_of),
            recommendation=recommendation,
        ).model_dump(),
        "graph": bundle["graph"],
        "baseline": baseline,
        "watch_hits": watch_hits,
        "kb_hits": kb_hits,
        "transactions": txs,
        "fact_issues": fact_issues,
        "can_sign": len(fact_issues) == 0 and (judge_validation["passed"] or not use_challenger),
        "elapsed_ms": elapsed_ms,
        "comparison": {
            "agent_ms": elapsed_ms,
            "tools_called": len(tool_trace),
            "elements_filled": sum(1 for e in report["elements"] if (e.get("value") or "").strip()),
            "elements_total": len(report["elements"]),
            "evidence_linkable": True,
            "note": "规则对照与 AI Judge 并排呈现，分歧交由调查员裁决。",
        },
    }
    attach_checklist(
        payload,
        counterparties=enrich_counterparties(db, alert["account_id"], txs, bundle.get("graph") or {}),
    )
    try:
        persist_investigation(db, payload)
        audit(f"case persisted {alert['id']}")
    except Exception as exc:
        warning(f"case persist skipped: {exc}")
    return payload
