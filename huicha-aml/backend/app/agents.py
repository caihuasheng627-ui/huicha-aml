from __future__ import annotations

import time

from sqlalchemy.orm import Session

from .knowledge import retrieve_for_alert
from .llm import enrich_full_report, enrich_judge
from .pipeline.cites import regulation_cites
from .pipeline.state import FAKE_ACCOUNT, RunOptions, StageDeps
from .tool_audit import bind_tool_context, reset_tool_context, tool

__all__ = [
    "FAKE_ACCOUNT",
    "enrich_full_report",
    "enrich_judge",
    "regulation_cites",
    "run_investigation",
    "search_knowledge_tool",
]


@tool("search_knowledge")
def search_knowledge_tool(alert_type: str, industry: str, as_of: str = "") -> list[dict]:
    return retrieve_for_alert(alert_type, industry, as_of=as_of)


def run_investigation(
    db: Session,
    alert_id: str,
    *,
    use_challenger: bool = True,
    inject_hallucination: bool = False,
    experiment_mode: bool = False,
    emit=None,
) -> dict:
    from .pipeline.runner import run_pipeline

    started = time.perf_counter()
    tool_trace: list = []
    tokens = bind_tool_context(db=db, alert_id=alert_id, trace=tool_trace)
    try:
        return run_pipeline(
            db,
            alert_id,
            options=RunOptions(
                use_challenger=use_challenger,
                inject_hallucination=inject_hallucination,
                experiment_mode=experiment_mode,
            ),
            deps=StageDeps(
                enrich_judge=enrich_judge,
                enrich_full_report=enrich_full_report,
                search_knowledge=search_knowledge_tool,
            ),
            started=started,
            tool_trace=tool_trace,
            emit=emit,
        )
    finally:
        reset_tool_context(tokens)
