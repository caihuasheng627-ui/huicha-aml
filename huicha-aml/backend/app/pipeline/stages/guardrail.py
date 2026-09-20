from __future__ import annotations

from ...decision import apply_guardrails
from ...report_draft import apply_policy_conclusion
from ..state import InvestigationState, StageContext


class GuardrailStage:
    name = "guardrail"
    role = "PolicyGuardrail"

    def run(self, state: InvestigationState, ctx: StageContext) -> None:
        guardrails = apply_guardrails(
            state.judge,
            watch_hits=state.bundle["watch_hits"],
            fact_issues=state.fact_issues,
        )
        state.guardrails = guardrails
        state.conclusion = guardrails["final_conclusion"]
        apply_policy_conclusion(state.report, guardrails)
