from __future__ import annotations

from ...analyst_rules import CONCLUSION_LABEL
from ...logging_util import warning
from ...report_draft import apply_full_text, render_report
from ...tools import fact_check
from ..state import FAKE_ACCOUNT, InvestigationState, StageContext


class ReporterStage:
    name = "reporter"
    role = "Reporter"

    def run(self, state: InvestigationState, ctx: StageContext) -> None:
        options = ctx.options
        alert = state.alert
        customer = state.customer
        bundle = state.bundle
        findings = state.findings
        conclusion = state.conclusion
        txs = state.txs
        analyst = state.analyst
        kb_hits = state.kb_hits
        sampling = state.sampling
        judge = state.judge
        judge_validation = state.judge_validation
        llm_findings = state.llm_findings
        privacy = state.privacy
        use_challenger = options.use_challenger

        report = render_report(
            alert,
            customer,
            bundle["baseline"],
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
                full_text, reporter_usage = ctx.deps.enrich_full_report(
                    db=ctx.db, privacy=privacy, context=report_context
                )
                apply_full_text(report, full_text, conclusion)
                report_issues = fact_check(report["full_text"], bundle["facts"])
                if report_issues:
                    fact_retry = True
                    full_text, reporter_usage = ctx.deps.enrich_full_report(
                        db=ctx.db,
                        privacy=privacy,
                        context=report_context,
                        prior_issues=report_issues,
                    )
                    apply_full_text(report, full_text, conclusion)
            except RuntimeError as exc:
                warning(f"Reporter 全文生成失败，使用确定性模板: {exc}")

        if options.inject_hallucination:
            poison = f"另发现未在工具结果中出现的对手账户 {FAKE_ACCOUNT}。"
            report["reason"] += poison
            report["full_text"] += "\n【注入幻觉演示】" + poison
        fact_issues = fact_check(report["full_text"], bundle["facts"])

        for i, row in enumerate(judge.get("rationale") or [], start=1):
            state.ev_graph.append(
                {
                    "evidence_id": f"EV-{alert['id']}-J{i:03d}",
                    "case_id": alert["id"],
                    "evidence_type": "MODEL",
                    "source_type": "judge",
                    "source_id": (row.get("evidence_ids") or [""])[0],
                    "description": row.get("text") or "",
                    "raw_reference": ",".join(row.get("evidence_ids") or []),
                    "timestamp": "",
                    "reliability": state.confidence,
                    "created_by": "judge",
                    "polarity": "support",
                    "metadata": {"confidence_kind": "llm_self_assessed_not_calibrated"},
                    "data_note": "synthetic",
                }
            )

        state.report = report
        state.reporter_usage = reporter_usage
        state.fact_retry = fact_retry
        state.fact_issues = fact_issues
