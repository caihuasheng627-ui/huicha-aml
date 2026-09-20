from __future__ import annotations

from ...models import Alert
from ...tools import plan_tool_names
from ..state import InvestigationState, StageContext


class PlannerStage:
    name = "planner"
    role = "Planner"

    def run(self, state: InvestigationState, ctx: StageContext) -> None:
        row = ctx.db.get(Alert, state.alert_id)
        alert_type = (row.alert_type if row else "") or ""
        state.planned = plan_tool_names(alert_type)
        if row:
            state.alert = {
                "id": row.id,
                "alert_type": row.alert_type,
                "account_id": row.account_id,
                "customer_id": row.customer_id,
                "created_at": row.created_at,
            }
