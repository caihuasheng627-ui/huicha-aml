from __future__ import annotations

import time

from ...analyst_rules import CONCLUSION_LABEL
from ...case_store import persist_investigation
from ...checklist import attach_checklist, enrich_counterparties
from ...decision import decision_claims
from ...llm import llm_model, llm_provider_label, usage_tokens
from ...logging_util import audit, warning
from ...prompts import prompt_version
from ...risk import CONCLUSION_TO_RECO, RECO_LABEL
from ...schema import InvestigationPlan, PlanStep, StructuredReport
from ...tools import ALLOWED_TOOLS, hard_fact_issues, yuan
from ...typology import tags_from_findings
from ...workflow import collect_sign_blockers
from ..cites import regulation_cites
from ..state import InvestigationState, StageContext


class AssembleStage:
    name = "assemble"
    role = "Assemble"

    def run(self, state: InvestigationState, ctx: StageContext) -> None:
        options = ctx.options
        alert = state.alert
        customer = state.customer
        bundle = state.bundle
        txs = state.txs
        kb_hits = state.kb_hits
        planned = state.planned
        as_of = state.as_of
        privacy = state.privacy
        findings = state.findings
        analyst = state.analyst
        sampling = state.sampling
        judge = state.judge
        judge_validation = state.judge_validation
        judge_repaired = state.judge_repaired
        fallback_reason = state.fallback_reason
        baseline_result = state.baseline_result
        guardrails = state.guardrails
        counterfactual_result = state.counterfactual
        evidence_sufficiency = state.evidence_sufficiency or {}
        verified_claims = state.verified_claims or []
        agent_reliability = state.agent_reliability or {}
        conclusion = state.conclusion
        confidence = state.confidence
        report = state.report
        fact_issues = state.fact_issues
        fact_retry = state.fact_retry
        ev_graph = state.ev_graph
        tool_trace = state.tool_trace
        use_challenger = options.use_challenger
        experiment_mode = options.experiment_mode
        judge_usage = state.judge_usage
        reporter_usage = state.reporter_usage

        plan = [
            f"按告警类型选择只读工具：{'、'.join(planned)}",
            "从流水、KYC、图谱和知识库提取支持/反向/缺失证据",
            "Privacy：姓名/账号/客户号占位后再出站，检漏失败则中止",
            "慧查agent 输出完整三档建议与逐条引用",
            "Skeptic 校验证据契约、谓词真值，并做有界最小证据集搜索",
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
                "role": "Privacy",
                "title": "进模脱敏与出站检漏",
                "content": (
                    f"已登记姓名 {len(privacy.name_to_mask)}、账号 {len(privacy.acct_to_mask)}、"
                    f"客户号 {len(privacy.customer_to_mask)}；出站 {privacy.egress_calls} 次，未放行明文。"
                ),
                "items": [
                    "姓名 → CLIENT_00n，账号 → ACCOUNT_00n，客户号 → CUST_00n",
                    "交易编号 TX-* 保留，供引用校验",
                    "工作台与签发稿仍为受控明文；SQLite 不加密",
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
                "title": "引用/谓词核验与有界最小证据集",
                "content": judge_validation["reason"],
                "items": [
                    *(i.get("message") or str(i) for i in judge_validation.get("issues") or []),
                    counterfactual_result.get("note") or "",
                    evidence_sufficiency.get("note") or "",
                    agent_reliability.get("note") or "",
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
        elapsed_ms = int((time.perf_counter() - state.started) * 1000)
        tokens = usage_tokens(judge_usage) + usage_tokens(reporter_usage)
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
            "evidence_sufficiency": evidence_sufficiency,
            "verified_claims": verified_claims,
            "agent_reliability": agent_reliability,
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
                "usage": {"judge": judge_usage, "reporter": reporter_usage, "total_tokens": tokens},
                "models": {"judge": llm_model("judge"), "reporter": llm_model("reporter")},
            },
            "privacy": privacy.receipt(),
            "conclusion": conclusion,
            "conclusion_label": CONCLUSION_LABEL[conclusion],
            "confidence": round(confidence, 2),
            "confidence_kind": "llm_self_assessed_not_calibrated" if use_challenger else "rule_score_not_calibrated",
            "report": report,
            "evidence": evidence,
            "evidence_graph": ev_graph,
            "claims": decision_claims(judge),
            "rejected_claims": judge_validation.get("issues") or [],
            "timeline": state.timeline,
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
                "agent_abstained": (agent_reliability.get("stance") == "abstain") if use_challenger else False,
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
            "baseline": bundle["baseline"],
            "watch_hits": bundle["watch_hits"],
            "kb_hits": kb_hits,
            "transactions": txs,
            "fact_issues": fact_issues,
            "sign_blockers": collect_sign_blockers(
                fact_issues=fact_issues,
                judge_validation=judge_validation,
                use_challenger=use_challenger,
                reliability=agent_reliability,
            ),
            "can_sign": (
                len(hard_fact_issues(fact_issues)) == 0
                and (judge_validation["passed"] or not use_challenger)
                and ((not use_challenger) or agent_reliability.get("stance", "committed") == "committed")
            ),
            "elapsed_ms": elapsed_ms,
            "comparison": {
                "agent_ms": elapsed_ms,
                "tools_called": len(tool_trace),
                "tokens": tokens,
                "elements_filled": sum(1 for e in report["elements"] if (e.get("value") or "").strip()),
                "elements_total": len(report["elements"]),
                "evidence_linkable": True,
                "note": "规则对照与慧查agent 并排呈现，分歧交由调查员裁决。",
            },
            "trace": state.trace,
        }
        attach_checklist(
            payload,
            counterparties=enrich_counterparties(ctx.db, alert["account_id"], txs, bundle.get("graph") or {}),
        )
        try:
            persist_investigation(ctx.db, payload)
            audit(f"case persisted {alert['id']}")
        except Exception as exc:
            warning(f"case persist skipped: {exc}")
        state.payload = payload
