from __future__ import annotations

from ...decision import normalize_judge, verify_judge
from ...predicates import case_facts
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
        use_challenger = options.use_challenger

        judge_usage: dict = {}
        judge_repaired = False
        fallback_reason = ""

        def _judge_once(prior_issues: list[dict] | None, transactions=None, findings_for_llm=None, allowed_for_prompt=None) -> tuple[dict, dict, dict]:
            from ..toolkit import judge_tools_enabled, run_judge_with_tools

            tx_in = transactions if transactions is not None else sample_txs
            findings_in = findings_for_llm if findings_for_llm is not None else llm_findings
            allowed_in = allowed_for_prompt if allowed_for_prompt is not None else prompt_allowed
            if judge_tools_enabled():
                raw, usage, extra_ids, extra_txs = run_judge_with_tools(
                    db=ctx.db,
                    privacy=privacy,
                    alert=alert,
                    customer=customer,
                    findings=findings_in,
                    transactions=tx_in,
                    baseline=baseline,
                    kb_hits=kb_hits,
                    allowed_evidence=allowed_in,
                    prior_issues=prior_issues,
                    tx_clusters=sampling["clusters"],
                    tx_summary=sampling["summary"],
                    account_id=state.account_id,
                    as_of=state.as_of,
                    search_knowledge=ctx.deps.search_knowledge,
                )
                if extra_ids:
                    state.allowed_evidence = sorted(set(state.allowed_evidence) | set(extra_ids))
                    state.allowed_set = set(state.allowed_evidence)
                    state.prompt_allowed = sorted(set(state.prompt_allowed) | set(extra_ids))
                    state.cite_set = set(state.prompt_allowed)
                    facts = state.bundle.get("facts") or {}
                    facts["tx_ids"] = sorted(set(facts.get("tx_ids") or []) | {i for i in extra_ids if str(i).startswith("TX-")})
                    facts["kb_ids"] = sorted(set(facts.get("kb_ids") or []) | {i for i in extra_ids if str(i).startswith("KB-")})
                    state.bundle["facts"] = facts
                if extra_txs:
                    seen = {t.get("id") for t in state.txs}
                    for row in extra_txs:
                        if row.get("id") and row["id"] not in seen:
                            state.txs.append(row)
                            seen.add(row["id"])
            else:
                raw, usage = ctx.deps.enrich_judge(
                    db=ctx.db,
                    privacy=privacy,
                    alert=alert,
                    customer=customer,
                    findings=findings_in,
                    transactions=tx_in,
                    baseline=baseline,
                    kb_hits=kb_hits,
                    allowed_evidence=allowed_in,
                    prior_issues=prior_issues,
                    tx_clusters=sampling["clusters"],
                    tx_summary=sampling["summary"],
                )
            decision = normalize_judge(raw, known_ids=state.allowed_set)
            facts = case_facts(transactions=state.txs, customer=customer, account_id=state.account_id)
            state.case_facts = facts
            return decision, verify_judge(decision, allowed_evidence=state.cite_set, facts=facts), usage

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

        conclusion = judge.get("disposition") or baseline_result["conclusion"]
        confidence = float(judge.get("confidence") or 0)
        confidence = max(0.0, min(1.0, confidence))

        state.judge = judge
        state.judge_validation = judge_validation
        state.judge_repaired = judge_repaired
        state.fallback_reason = fallback_reason
        state.judge_usage = judge_usage
        state.conclusion = conclusion
        state.confidence = confidence
