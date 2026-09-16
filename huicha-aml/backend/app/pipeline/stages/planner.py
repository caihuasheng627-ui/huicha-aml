from __future__ import annotations

from ..state import InvestigationState, StageContext


class PlannerStage:
    name = "planner"
    role = "Planner"

    def run(self, state: InvestigationState, ctx: StageContext) -> None:
        # 工具清单由 Collector 内 collect_bundle → plan_tool_names 决定，避免重复 get_alert 污染 tool_trace。
        return None
