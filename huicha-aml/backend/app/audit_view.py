"""把已有审计/工具轨迹摊成只读时间线，不另建日志库。"""

from __future__ import annotations

import json

KIND_TITLE = {
    "tool": "调取工具",
    "pipeline": "生成草稿",
    "validator": "证据校验",
    "reject": "Claim 未进分",
    "human": "人工处置",
    "checklist": "补证清单",
    "audit": "审计",
}


def _parse_detail(raw: str) -> dict:
    try:
        data = json.loads(raw or "")
        return data if isinstance(data, dict) else {"summary": str(raw or "")}
    except Exception:
        return {"summary": raw or ""}


def build_audit_timeline(
    logs: list,
    payload: dict | None = None,
    *,
    format_cn,
    human_note: str = "",
    human_decision: str = "",
) -> list[dict]:
    events: list[dict] = []
    payload = payload or {}
    for x in logs or []:
        action = getattr(x, "action", "") or ""
        parsed = _parse_detail(getattr(x, "detail", "") or "")
        if action.startswith("tool"):
            kind = "tool"
            title = f"工具 {parsed.get('tool') or action.split(':', 1)[-1]}"
            detail = f"{parsed.get('records', '—')} 条 · {parsed.get('elapsed_ms', '—')} ms"
        elif action == "investigate":
            kind = "pipeline"
            title = "生成调查草稿"
            detail = parsed.get("summary") or ""
        elif action == "validator":
            kind = "validator"
            title = "Validator"
            detail = parsed.get("summary") or str((parsed.get("validator_result") or {}).get("reason") or "")
        elif action == "decide":
            kind = "human"
            title = "人工签发"
            detail = parsed.get("summary") or human_note or human_decision
        elif action == "checklist":
            kind = "checklist"
            title = "写入补证备注"
            detail = parsed.get("summary") or ""
        else:
            kind = "audit"
            title = action or "记录"
            detail = parsed.get("summary") or getattr(x, "detail", "") or ""
        actor = getattr(x, "actor", "") or ""
        if actor in {"agent", "tool"}:
            actor = "系统"
        events.append(
            {
                "id": f"log-{getattr(x, 'id', len(events))}",
                "at": format_cn(getattr(x, "created_at", None)),
                "actor": actor,
                "kind": kind,
                "action": action,
                "title": title,
                "detail": str(detail)[:240],
            }
        )
    seen_reject = any(e["kind"] == "reject" for e in events)
    if not seen_reject:
        for i, r in enumerate(payload.get("rejected_claims") or []):
            reason = (r.get("validation") or {}).get("reason") or r.get("claim") or ""
            events.append(
                {
                    "id": f"reject-{i}",
                    "at": "",
                    "actor": "Validator",
                    "kind": "reject",
                    "action": "reject_claim",
                    "title": KIND_TITLE["reject"],
                    "detail": str(reason)[:240],
                }
            )
    if payload.get("tool_trace") and not any(e["kind"] == "tool" for e in events):
        for i, t in enumerate(payload.get("tool_trace") or []):
            events.append(
                {
                    "id": f"trace-{i}",
                    "at": "",
                    "actor": "系统",
                    "kind": "tool",
                    "action": f"tool:{t.get('tool')}",
                    "title": f"工具 {t.get('tool')}",
                    "detail": f"{t.get('records', '—')} 条 · {t.get('elapsed_ms', '—')} ms",
                }
            )
    return events
