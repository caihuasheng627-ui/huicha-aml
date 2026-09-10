from __future__ import annotations

import contextvars
import json
import time
from functools import wraps
from typing import Any, Callable

from sqlalchemy.orm import Session

_alert_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("tool_alert_id", default=None)
_db: contextvars.ContextVar[Session | None] = contextvars.ContextVar("tool_db", default=None)
_trace: contextvars.ContextVar[list | None] = contextvars.ContextVar("tool_trace", default=None)


def bind_tool_context(*, db: Session, alert_id: str, trace: list):
    return [_db.set(db), _alert_id.set(alert_id), _trace.set(trace)]


def reset_tool_context(tokens: list) -> None:
    for t in reversed(tokens):
        t.var.reset(t)


def _record_count(result: Any) -> int:
    if result is None:
        return 0
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        if isinstance(result.get("nodes"), list):
            return len(result["nodes"])
        if isinstance(result.get("hits"), list):
            return len(result["hits"])
        return 1
    return 1


def tool(name: str) -> Callable:
    """装饰只读工具：记录耗时/条数到 tool_trace，并追加 AuditLog。"""

    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            started = time.perf_counter()
            ok = True
            err = ""
            result: Any = None
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as e:
                ok = False
                err = str(e)
                raise
            finally:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                records = _record_count(result) if ok else 0
                entry = {
                    "tool": name,
                    "ok": ok,
                    "records": records,
                    "elapsed_ms": elapsed_ms,
                    "error": err[:200] if err else "",
                }
                trace = _trace.get()
                if trace is not None:
                    trace.append(entry)
                db = _db.get()
                alert_id = _alert_id.get()
                if db is not None and alert_id:
                    try:
                        from .models import AuditLog, utcnow

                        db.add(
                            AuditLog(
                                alert_id=alert_id,
                                actor="tool",
                                action=f"tool:{name}",
                                detail=json.dumps(
                                    {
                                        "tool": name,
                                        "ok": ok,
                                        "records": records,
                                        "elapsed_ms": elapsed_ms,
                                    },
                                    ensure_ascii=False,
                                ),
                                created_at=utcnow(),
                            )
                        )
                    except Exception:
                        pass

        wrapper._tool_name = name  # type: ignore[attr-defined]
        return wrapper

    return deco
