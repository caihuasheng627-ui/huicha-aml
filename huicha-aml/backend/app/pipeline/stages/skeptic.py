from __future__ import annotations

from ...decision import normalize_judge, verified_claims_from_judge, verify_judge
from ...evidence_sufficiency import default_counterfactual, drop_findings, search_minimal_set
from ...predicates import case_facts
from ...reliability import compute_reliability
from ...sampler import compact_findings_for_llm
from ..state import InvestigationState, StageContext


class SkepticStage:
    name = "skeptic"
    role = "Skeptic"

    def run(self, state: InvestigationState, ctx: StageContext) -> None:
        options = ctx.options
        judge = state.judge
        judge_validation = state.judge_validation
        findings = state.findings
        cite_set = state.cite_set
        allowed_set = state.allowed_set
        sampling = state.sampling
        sample_txs = sampling["sample"]
        citable = state.citable
        prompt_allowed = state.prompt_allowed
        alert = state.alert
        customer = state.customer
        baseline = state.bundle["baseline"]
        kb_hits = state.kb_hits
        privacy = state.privacy
        use_challenger = options.use_challenger
        verified_claims = verified_claims_from_judge(judge) if judge_validation.get("passed") else []
        counterfactual_result = default_counterfactual(judge)
        sufficiency = {
            "method": "bounded_greedy",
            "verified": True,
            "budget_exhausted": False,
            "performed": False,
            "rounds": 0,
            "max_rounds": 3,
            "max_candidates": 4,
            "minimal_sufficient_set": [],
            "necessary_ids": [],
            "redundant_ids": [],
            "candidates": [],
            "note": "未执行有界证据搜索。",
        }

        def run_round(removed_ids: set[str], message: str) -> dict:
            cf_cite = cite_set - removed_ids
            cf_findings = drop_findings(findings, removed_ids)
            cf_llm_findings = compact_findings_for_llm(cf_findings, keep_ids=citable - removed_ids)
            cf_sample = [t for t in sample_txs if t.get("id") not in removed_ids]
            cf_txs = [t for t in state.txs if t.get("id") not in removed_ids]
            cf_facts = case_facts(transactions=cf_txs, customer=customer, account_id=state.account_id)
            raw_cf, _ = ctx.deps.enrich_judge(
                db=ctx.db,
                privacy=privacy,
                alert=alert,
                customer=customer,
                findings=cf_llm_findings,
                transactions=cf_sample,
                baseline=baseline,
                kb_hits=kb_hits,
                allowed_evidence=[e for e in prompt_allowed if e not in removed_ids],
                prior_issues=[{"kind": "counterfactual", "message": message}],
                tx_clusters=sampling["clusters"],
                tx_summary=sampling["summary"],
            )
            cf_judge = normalize_judge(raw_cf, known_ids=allowed_set - removed_ids)
            cf_valid = verify_judge(cf_judge, allowed_evidence=cf_cite, facts=cf_facts)
            return {"judge": cf_judge, "validation": cf_valid, "error": ""}

        if use_challenger and judge_validation.get("passed") and judge.get("supporting_evidence_ids"):
            sufficiency, counterfactual_result = search_minimal_set(
                judge=judge,
                findings=findings,
                verified_claims=verified_claims,
                run_round=run_round,
                baseline=state.baseline_result,
            )
        elif judge_validation.get("passed"):
            sufficiency["minimal_sufficient_set"] = list(
                dict.fromkeys(
                    [
                        *(judge.get("supporting_evidence_ids") or []),
                        *[eid for row in (judge.get("rationale") or []) for eid in (row.get("evidence_ids") or [])],
                    ]
                )
            )
            sufficiency["note"] = "无支持证据簇，沿用当前引用。"
            sufficiency["verified"] = True

        reliability = compute_reliability(
            use_challenger=use_challenger,
            judge=judge,
            judge_validation=judge_validation,
            fallback_reason=state.fallback_reason,
            baseline=state.baseline_result,
            counterfactual=counterfactual_result,
            evidence_sufficiency=sufficiency,
        )
        state.counterfactual = counterfactual_result
        state.evidence_sufficiency = sufficiency
        state.verified_claims = verified_claims
        state.agent_reliability = reliability
