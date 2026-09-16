"""Judge 可选的受控只读补证。默认关闭；HUICHA_JUDGE_TOOLS=1 时最多两轮工具调用。"""

from __future__ import annotations

import json
import os
import re

from sqlalchemy.orm import Session

from .. import llm as llm_mod
from ..prompts import PROMPTS, prompt_version
from ..tool_audit import _trace
from ..tools import get_related_accounts, get_timeline, get_transactions, search_regulation

JUDGE_TOOL_NAMES = {
    "get_transactions",
    "get_related_accounts",
    "get_timeline",
    "search_regulation",
    "search_knowledge",
}

JUDGE_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_transactions",
            "description": "读取本案主体账户在给定窗口内的流水。",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {"type": "string"},
                    "window_start": {"type": "string"},
                    "window_end": {"type": "string"},
                },
                "required": ["account_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_related_accounts",
            "description": "读取本案主体账户的一度对手。",
            "parameters": {
                "type": "object",
                "properties": {"account_id": {"type": "string"}},
                "required": ["account_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_timeline",
            "description": "读取本案主体账户时间线。",
            "parameters": {
                "type": "object",
                "properties": {"account_id": {"type": "string"}},
                "required": ["account_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_regulation",
            "description": "检索法规条款。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "as_of": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "按本案告警类型检索作业口径与法规。",
            "parameters": {
                "type": "object",
                "properties": {
                    "alert_type": {"type": "string"},
                    "industry": {"type": "string"},
                    "as_of": {"type": "string"},
                },
            },
        },
    },
]


def _sanitize_for_llm(obj, privacy):
    blob = json.dumps(obj, ensure_ascii=False)
    if privacy:
        blob = privacy.mask_text(blob)
    blob = re.sub(r"6222-[A-Z0-9\-]+", "ACCOUNT_UNKNOWN", blob)
    return json.loads(blob)


def judge_tools_enabled() -> bool:
    return os.getenv("HUICHA_JUDGE_TOOLS", "").strip().lower() in {"1", "true", "yes", "on"}


def _record_denied(name: str, reason: str) -> None:
    trace = _trace.get()
    if trace is not None:
        trace.append(
            {
                "tool": name,
                "ok": False,
                "records": 0,
                "elapsed_ms": 0,
                "error": reason,
            }
        )


def execute_judge_tool(
    name: str,
    args: dict,
    *,
    db: Session,
    account_id: str,
    as_of: str,
    alert_type: str,
    industry: str,
    search_knowledge,
) -> tuple[object, list[str], list[dict]]:
    if name not in JUDGE_TOOL_NAMES:
        _record_denied(name, "工具不在 Judge 白名单")
        return {"error": f"工具不在白名单：{name}"}, [], []
    if "account_id" in args and str(args.get("account_id") or "") not in {"", account_id}:
        _record_denied(name, f"跨账户请求已拒绝：{args.get('account_id')}")
        return {"error": "只允许查询本案主体账户"}, [], []

    new_ids: list[str] = []
    new_txs: list[dict] = []
    if name == "get_transactions":
        rows = get_transactions(
            db,
            account_id,
            window_start=str(args.get("window_start") or ""),
            window_end=str(args.get("window_end") or ""),
        )
        compact = rows[:20]
        new_txs = compact
        new_ids = [t["id"] for t in compact if t.get("id")]
        return compact, new_ids, new_txs
    if name == "get_related_accounts":
        return get_related_accounts(db, account_id), [], []
    if name == "get_timeline":
        rows = get_timeline(db, account_id)
        new_ids = [r.get("tx_id") or r.get("evidence_id") for r in rows[:20] if r.get("tx_id") or r.get("evidence_id")]
        return rows[:20], [i for i in new_ids if i], []
    if name == "search_regulation":
        hits = search_regulation(str(args.get("query") or ""), as_of=str(args.get("as_of") or as_of))
        new_ids = [h.get("id") for h in hits if h.get("id")]
        return hits, [i for i in new_ids if i], []
    if name == "search_knowledge":
        hits = search_knowledge(alert_type, industry, as_of)
        new_ids = [h.get("id") for h in hits if h.get("id")]
        return hits, [i for i in new_ids if i], []
    return {"error": "未执行"}, [], []


def run_judge_with_tools(
    *,
    db: Session,
    privacy,
    alert: dict,
    customer: dict,
    findings: list[dict],
    transactions: list[dict],
    baseline: dict,
    kb_hits: list[dict],
    allowed_evidence: list[str],
    prior_issues: list[dict] | None,
    tx_clusters: list[dict] | None,
    tx_summary: dict | None,
    account_id: str,
    as_of: str,
    search_knowledge,
) -> tuple[dict, dict, list[str], list[dict]]:
    kind = prompt_version("judge")
    context = llm_mod.build_judge_context(
        alert=alert,
        customer=customer,
        findings=findings,
        transactions=transactions,
        baseline=baseline,
        kb_hits=kb_hits,
        allowed_evidence=allowed_evidence,
        prior_issues=prior_issues,
        tx_clusters=tx_clusters,
        tx_summary=tx_summary,
    )
    payload = privacy.prepare_for_llm(context) if privacy else context
    system = PROMPTS[kind] + " 如需补充只读证据，可调用提供的工具；完成后仍须输出完整 JSON 对象。"
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    new_ids: list[str] = []
    new_txs: list[dict] = []
    model = llm_mod.llm_model("judge")
    usage: dict = {}
    text = ""
    for round_i in range(3):
        allow_tools = round_i < 2
        text, usage = llm_mod.chat(
            messages,
            temperature=0.0,
            max_tokens=llm_mod.JUDGE_MAX_TOKENS,
            model=model,
            tools=JUDGE_TOOL_SCHEMAS if allow_tools else None,
        )
        calls = usage.get("tool_calls") or []
        if calls and allow_tools:
            messages.append(
                {
                    "role": "assistant",
                    "content": text or "",
                    "tool_calls": _sanitize_for_llm(calls, privacy),
                }
            )
            for call in calls:
                fn = (call.get("function") or {}) if isinstance(call, dict) else {}
                name = str(fn.get("name") or "")
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except json.JSONDecodeError:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                result, ids, txs = execute_judge_tool(
                    name,
                    args,
                    db=db,
                    account_id=account_id,
                    as_of=as_of,
                    alert_type=alert.get("alert_type") or "",
                    industry=customer.get("industry") or "",
                    search_knowledge=search_knowledge,
                )
                new_ids.extend(ids)
                new_txs.extend(txs)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(call.get("id") or ""),
                        "content": json.dumps(_sanitize_for_llm(result, privacy), ensure_ascii=False)[:8000],
                    }
                )
            continue
        data = llm_mod._parse_model_json(text, usage, role="Judge")
        return llm_mod._unmask_value(data, privacy), usage, list(dict.fromkeys(new_ids)), new_txs
    raise RuntimeError("Judge 工具循环未产出 JSON")
