from __future__ import annotations

import time

from sqlalchemy.orm import Session

from .analyst_rules import CONCLUSION_LABEL, analyze, rule_prior, score_to_conclusion
from .case_store import evidence_case_index, persist_investigation
from .checklist import attach_checklist, enrich_counterparties
from .decision import apply_guardrails, decision_claims, normalize_judge, rule_baseline, verify_judge
from .evidence import build_evidence_graph, source_ids_of
from .knowledge import retrieve_for_alert
from .llm import enrich_challenger, enrich_full_report, enrich_judge, enrich_report_reason, llm_model, llm_provider_label
from .predicates import case_facts
from .logging_util import audit, warning
from .privacy import PrivacyMap
from .prompts import prompt_version
from .report_draft import apply_full_text, apply_reason, render_report
from .risk import CONCLUSION_TO_RECO, RECO_LABEL, aggregate, counterfactual, score_to_level
from .schema import InvestigationPlan, PlanStep, RegulationCite, StructuredReport
from .tool_audit import bind_tool_context, reset_tool_context, tool
from .sampler import citable_tx_ids, compact_findings_for_llm, select_for_judge, visible_evidence_ids
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
from .validator import DELTA_BOUND, filter_challenger_items

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
            win = bundle.get("tx_window") or {}
            for p in peers:
                for extra in get_transactions(
                    db,
                    p["account_id"],
                    window_start=win.get("start") or "",
                    window_end=win.get("end") or "",
                ):
                    if extra["id"] not in seen:
                        extra["source"] = "peer"
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
        return {
            "challenger": [],
            "usage": {},
            "rule_prior": 0.0,
            "llm_delta": 0.0,
            "raw_delta": 0.0,
            "rejected": [],
            "hints": [],
        }
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
        raw_ch, usage = enrich_challenger(
            db=db,
            privacy=privacy,
            alert=alert,
            customer=customer,
            findings=findings,
            baseline=baseline,
            kb_hits=kb_hits,
            score_hints=hints,
            allowed_evidence=allowed_evidence,
            transactions=txs,
        )
    except RuntimeError as e:
        warning(f"Challenger 失败，仅保留规则先验: {e}")
        raw_ch, usage = [], {}
    evidence_case = evidence_case_index(db)
    for eid in allowed_evidence:
        if not str(eid).startswith("KB-"):
            evidence_case[eid] = alert["id"]
    facts = case_facts(transactions=txs, customer=customer, account_id=alert.get("account_id") or "")
    challenger, llm_delta, rejected = filter_challenger_items(
        raw_ch,
        allowed=set(allowed_evidence),
        case_id=alert["id"],
        evidence_case=evidence_case,
        facts=facts,
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
    raw_delta = round(sum(float(c.get("delta") or 0) for c in challenger), 4)
    return {
        "challenger": challenger,
        "usage": usage,
        "rule_prior": prior,
        "llm_delta": llm_delta,
        "raw_delta": raw_delta,
        "rejected": rejected,
        "hints": hints,
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
    sampling = select_for_judge(
        alert=alert,
        account_id=account_id,
        txs=txs,
        findings=findings,
        baseline=baseline,
    )
    sample_txs = sampling["sample"]
    citable = citable_tx_ids(sample_txs, sampling["clusters"])
    sampling["citable_tx_ids"] = sorted(citable)
    llm_findings = compact_findings_for_llm(findings, keep_ids=citable)
    ev_graph = build_evidence_graph(alert["id"], bundle, kb_hits)
    allowed_evidence = sorted(
        source_ids_of(ev_graph)
        | {t["id"] for t in txs}
        | {customer["id"], alert["account_id"]}
        | {e for f in findings for e in f.get("evidence_ids", [])}
    )
    prompt_allowed = visible_evidence_ids(
        sample=sample_txs,
        clusters=sampling["clusters"],
        findings=llm_findings,
        extra=[customer["id"], alert["account_id"], *[h["id"] for h in kb_hits if h.get("id")]],
    )
    # 报告回查时，告警号与证据号是本案已知引用，不应被拆成数字片段误报。
    bundle["facts"]["ref_ids"] = sorted(set(bundle["facts"].get("ref_ids") or []) | {alert["id"]} | set(allowed_evidence))

    judge_usage: dict = {}
    judge_repaired = False
    fallback_reason = ""
    allowed_set = set(allowed_evidence)
    cite_set = set(prompt_allowed)

    def _judge_once(prior_issues: list[dict] | None, transactions=None, findings_for_llm=None, allowed_for_prompt=None) -> tuple[dict, dict, dict]:
        raw, usage = enrich_judge(
            db=db,
            privacy=privacy,
            alert=alert,
            customer=customer,
            findings=findings_for_llm if findings_for_llm is not None else llm_findings,
            transactions=transactions if transactions is not None else sample_txs,
            baseline=baseline,
            kb_hits=kb_hits,
            allowed_evidence=allowed_for_prompt if allowed_for_prompt is not None else prompt_allowed,
            prior_issues=prior_issues,
            tx_clusters=sampling["clusters"],
            tx_summary=sampling["summary"],
        )
        decision = normalize_judge(raw, known_ids=allowed_set)
        return decision, verify_judge(decision, allowed_evidence=cite_set), usage

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
                "missing_evidence": ["慧查agent 调用失败，须人工完整复核"],
                "rationale": [],
                "next_actions": ["人工复核规则对照与原始证据"],
            }
            judge_validation = {
                "passed": False,
                "issues": [{"kind": "judge_failure", "message": fallback_reason}],
                "citation_count": 0,
                "invalid_ids": [],
                "score_kind": "fallback",
                "reason": "慧查agent 失败，已降级为规则对照",
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
            "missing_evidence": ["慧查agent 已关闭，当前仅展示规则对照"],
            "rationale": [],
            "next_actions": ["启用慧查agent 或由调查员人工研判"],
        }
        judge_validation = {
            "passed": True,
            "issues": [],
            "citation_count": 0,
            "invalid_ids": [],
            "score_kind": "rule_only_ablation",
            "reason": "实验模式：慧查agent 已关闭",
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
        cf_cite = cite_set - removed_ids
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
            cf_llm_findings = compact_findings_for_llm(cf_findings, keep_ids=citable - removed_ids)
            cf_sample = [t for t in sample_txs if t.get("id") not in removed_ids]
            raw_cf, _ = enrich_judge(
                db=db,
                privacy=privacy,
                alert=alert,
                customer=customer,
                findings=cf_llm_findings,
                transactions=cf_sample,
                baseline=baseline,
                kb_hits=kb_hits,
                allowed_evidence=[e for e in prompt_allowed if e not in removed_ids],
                prior_issues=[
                    {
                        "kind": "counterfactual",
                        "message": f"移除指标「{(key_finding or {}).get('title') or key_id}」及其证据后重新判断",
                    }
                ],
                tx_clusters=sampling["clusters"],
                tx_summary=sampling["summary"],
            )
            cf_judge = normalize_judge(raw_cf, known_ids=allowed_set - removed_ids)
            cf_valid = verify_judge(cf_judge, allowed_evidence=cf_cite)
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
        sampling=sampling,
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
            "findings": llm_findings,
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
            "transaction_summary": sampling["summary"],
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
        "慧查agent 输出完整三档建议与逐条引用",
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
            "content": (
                f"窗口内 {sampling['summary']['total']} 笔，进模 {sampling['summary']['sampled']} 笔，"
                f"其余按 {len(sampling['clusters'])} 个簇汇总；知识 {len(kb_hits)} 条、工具 {len(tool_trace)} 次。"
            ),
            "items": [
                f"工具：{name}" for name in planned
            ] + [
                f"抽数：{sampling['summary']['omitted']} 笔未进模，簇合计 {sampling['summary']['in_count']} 入 / {sampling['summary']['out_count']} 出",
            ],
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
        "note": "最终建议来自通过证据契约的慧查agent；规则分仅作对照，护栏仅作政策边界。",
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
        "sampling": sampling,
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
            "label": "慧查agent",
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
            "provider": llm_provider_label(),
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
            transaction_summary=(
                f"流入{len(analyst['inflow'])} 流出{len(analyst['outflow'])}；"
                f"窗口{sampling['summary']['total']}笔/进模{sampling['summary']['sampled']}笔"
            ),
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
            "note": "规则对照与慧查agent 并排呈现，分歧交由调查员裁决。",
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


def _run_investigation_inner(
    db: Session,
    alert_id: str,
    *,
    use_challenger: bool,
    inject_hallucination: bool,
    experiment_mode: bool,
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
    raw_delta = float(ch.get("raw_delta") or 0)
    clamped_delta = float(llm_delta)
    delta_clamped = abs(raw_delta - clamped_delta) > 1e-9
    delta_suppressed = False
    pre_llm = base_score + rule_prior_v
    # 底分+先验已是排除时，再叠负 Δ 只会砸到 0.05 展示下限，不改档。
    if score_to_conclusion(max(0.0, pre_llm)) == "exclude" and llm_delta < 0:
        delta_suppressed = True
        llm_delta = 0.0
        for f in risk_factors:
            if f.get("code") == "challenger-llm":
                f["delta"] = 0.0

    if use_challenger:
        for i, c in enumerate(challenger, start=1):
            ev_graph.append(
                {
                    "evidence_id": f"EV-{alert['id']}-C{i:03d}",
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
                    "metadata": {
                        "delta": c.get("delta"),
                        "predicate": c.get("predicate") or "",
                        "score_kind": (c.get("validation") or {}).get("score_kind") or "",
                    },
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
                    (
                        f"{c.get('claim') or c['title']}（delta={c.get('delta', 0):+.2f}，"
                        f"谓词 {c.get('predicate') or '无'}，证据 {','.join(c.get('evidence_ids') or []) or '无'}）："
                        f"{c.get('detail') or ''}"
                    )
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
                    "调分须 predicate_verified；support_score 不是语义置信度。"
                ),
                "items": [r.get("validation", {}).get("reason") or "ok" for r in rejected_claims]
                or ["本轮调分 Claim 均通过谓词执行"],
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
    raw_score = base_score + rule_prior_v + llm_delta
    score = max(0.05, min(0.95, raw_score))
    conclusion = score_to_conclusion(score)
    risk["final"] = round(score, 4)
    risk["raw"] = round(raw_score, 4)
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
            "content": f"理由由 {llm_provider_label()} {llm_model()} 生成（脱敏进模）；事实不匹配不可签发。",
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
    initial_conclusion = score_to_conclusion(base_score)
    overbound = [
        r
        for r in rejected_claims
        if "超出" in str((r.get("validation") or {}).get("reason") or "")
    ]
    validator_failed = bool(use_challenger and rejected_claims and not challenger)
    support_ids = []
    seen_s: set[str] = set()
    for f in findings:
        if f.get("code") in {"pattern-peer", "thin"}:
            continue
        for eid in f.get("evidence_ids") or []:
            if eid and eid not in seen_s:
                seen_s.add(eid)
                support_ids.append(eid)
    counter_ids = []
    seen_c: set[str] = set()
    for c in challenger:
        for eid in c.get("evidence_ids") or []:
            if eid and eid not in seen_c:
                seen_c.add(eid)
                counter_ids.append(eid)
    invalid_ids = []
    seen_i: set[str] = set()
    for r in rejected_claims:
        for eid in r.get("evidence_ids") or []:
            if eid and eid not in seen_i:
                seen_i.add(eid)
                invalid_ids.append(eid)
    kb_rule_ids = [h["id"] for h in kb_hits if h.get("kind") == "regulation"]
    validator_result = {
        "passed": not validator_failed,
        "score_kind": "id_membership",
        "kept": len(challenger),
        "rejected": len(rejected_claims),
        "overbound": len(overbound),
        "delta_clamped": delta_clamped,
        "reason": (
            "Challenger 输出未通过证据校验"
            if validator_failed
            else "证据编号属于本案件工具结果（不是语义支持度）"
        ),
    }
    challenger_run = {
        "enabled": use_challenger,
        "experiment_mode": experiment_mode,
        "ablation": not use_challenger,
        "label": "AI反向质询",
        "delta_bound": DELTA_BOUND,
        "initial_score": round(base_score, 4),
        "initial_conclusion": initial_conclusion,
        "initial_label": CONCLUSION_LABEL[initial_conclusion],
        "rule_prior": rule_prior_v,
        "llm_delta": llm_delta,
        "raw_delta": raw_delta,
        "clamped_delta": clamped_delta,
        "delta_clamped": delta_clamped,
        "delta_suppressed": delta_suppressed,
        "final_score": round(score, 4),
        "final_conclusion": conclusion,
        "final_label": CONCLUSION_LABEL[conclusion],
        "support_ids": support_ids[:12],
        "counter_ids": counter_ids[:12],
        "invalid_ids": invalid_ids[:12],
        "rule_ids": kb_rule_ids[:8],
        "claims": [
            {
                "claim": c.get("claim") or c.get("title") or "",
                "detail": c.get("detail") or "",
                "evidence_ids": c.get("evidence_ids") or [],
                "delta": c.get("delta") or 0,
                "polarity": "counter" if float(c.get("delta") or 0) < 0 else "support",
            }
            for c in challenger
        ],
        "validator": validator_result,
    }
    payload = {
        "alert": alert,
        "customer": customer,
        "plan": plan,
        "steps": steps,
        "tool_trace": tool_trace,
        "findings": findings,
        "challenger": challenger,
        "use_challenger": use_challenger,
        "case_challenger_enabled": use_challenger,
        "experiment_mode": experiment_mode,
        "inject_hallucination": inject_hallucination,
        "challenger_run": challenger_run,
        "validator_result": validator_result,
        "scoring": {
            "base": round(base_score, 4),
            "rule_prior": rule_prior_v,
            "llm_delta": llm_delta,
            "llm_clamped": clamped_delta,
            "raw": round(raw_score, 4),
            "final": round(score, 4),
            "delta_suppressed": delta_suppressed,
        },
        "llm": {
            "challenger": use_challenger,
            "reporter": True,
            "provider": llm_provider_label(),
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
            regulation_basis=regulation_cites(kb_hits, as_of),
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
    attach_checklist(
        payload,
        counterparties=enrich_counterparties(db, alert["account_id"], txs, bundle.get("graph") or {}),
    )
    try:
        persist_investigation(db, payload)
        audit(f"case persisted {alert['id']}")
    except Exception as e:
        warning(f"case persist skipped: {e}")
    return payload
