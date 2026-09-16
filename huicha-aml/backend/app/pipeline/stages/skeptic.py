from __future__ import annotations

from ...decision import normalize_judge, verify_judge
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

        state.counterfactual = counterfactual_result
