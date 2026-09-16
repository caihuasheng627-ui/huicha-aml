from __future__ import annotations

from ...analyst_rules import CONCLUSION_LABEL
from ...decision import apply_guardrails, normalize_judge, verify_judge
from ...typology import tags_from_findings
from ..state import InvestigationState, StageContext


class JudgeStage:
    name = "judge"
    role = "Judge"

    def run(self, state: InvestigationState, ctx: StageContext) -> None:
        options = ctx.options
        alert = state.alert
        customer = state.customer
        findings = state.findings
        baseline = state.bundle["baseline"]
        kb_hits = state.kb_hits
        sampling = state.sampling
        sample_txs = sampling["sample"]
        llm_findings = state.llm_findings
        prompt_allowed = state.prompt_allowed
        allowed_set = state.allowed_set
        cite_set = state.cite_set
        baseline_result = state.baseline_result
        privacy = state.privacy
        watch_hits = state.bundle["watch_hits"]
        use_challenger = options.use_challenger

        judge_usage: dict = {}
        judge_repaired = False
        fallback_reason = ""

        def _judge_once(prior_issues: list[dict] | None, transactions=None, findings_for_llm=None, allowed_for_prompt=None) -> tuple[dict, dict, dict]:
            raw, usage = ctx.deps.enrich_judge(
                db=ctx.db,
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

        state.judge = judge
        state.judge_validation = judge_validation
        state.judge_repaired = judge_repaired
        state.fallback_reason = fallback_reason
        state.judge_usage = judge_usage
        state.guardrails = guardrails
        state.conclusion = conclusion
        state.confidence = confidence
