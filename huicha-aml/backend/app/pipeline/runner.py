from __future__ import annotations

import time
from typing import Callable

from sqlalchemy.orm import Session

from ..llm import usage_tokens
from .stages import STAGES
from .state import InvestigationState, RunOptions, StageContext, StageDeps


def _noop(_event: dict) -> None:
    return None


def run_pipeline(
    db: Session,
    alert_id: str,
    *,
    options: RunOptions,
    deps: StageDeps,
    started: float,
    tool_trace: list,
    emit: Callable[[dict], None] | None = None,
) -> dict:
    emit_fn = emit or _noop
    state = InvestigationState(
        alert_id=alert_id,
        started=started,
        tool_trace=tool_trace,
        options=options,
    )
    ctx = StageContext(db=db, deps=deps, options=options, emit=emit_fn)
    for stage in STAGES:
        event_base = {"event": "stage", "stage": stage.name, "role": stage.role}
        emit_fn({**event_base, "status": "started"})
        t0 = time.perf_counter()
        try:
            stage.run(state, ctx)
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            state.trace.append(
                {
                    "stage": stage.name,
                    "role": stage.role,
                    "elapsed_ms": elapsed_ms,
                    "ok": False,
                    "error": str(exc)[:300],
                    "llm_calls": 0,
                    "tokens": 0,
                    "cached": False,
                }
            )
            emit_fn({**event_base, "status": "finished", "elapsed_ms": elapsed_ms, "ok": False})
            raise
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        usage = _stage_usage(stage.role, state)
        state.trace.append(
            {
                "stage": stage.name,
                "role": stage.role,
                "elapsed_ms": elapsed_ms,
                "ok": True,
                "error": "",
                "llm_calls": usage["llm_calls"],
                "tokens": usage["tokens"],
                "cached": usage["cached"],
            }
        )
        emit_fn({**event_base, "status": "finished", "elapsed_ms": elapsed_ms, "ok": True})
    return state.payload or {}


def _stage_usage(role: str, state: InvestigationState) -> dict:
    blob = {}
    if role == "Judge":
        blob = state.judge_usage or {}
    elif role == "Reporter":
        blob = state.reporter_usage or {}
    tokens = usage_tokens(blob) if isinstance(blob, dict) else 0
    cached = bool(blob.get("cached")) if isinstance(blob, dict) else False
    llm_calls = 1 if blob else 0
    return {"llm_calls": llm_calls, "tokens": tokens, "cached": cached}
