"""把案件材料渲染成调查人员会粘进聊天框的纯文本，供 A0/A1。

不输出金标、极性、规则层 code、知识库命中。流水号与调查记录号保留，
否则引用有效率无法和产品组公平比较。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.prompts import PROMPTS  # noqa: E402

A0_SYSTEM = (
    "你是反洗钱调查人员。只根据材料判断本案应排除、继续观察还是建议上报。"
    "只输出一个 JSON："
    '{"disposition":"exclude|observe|suggest_report","confidence":0到1,'
    '"reasons":[{"text":"...","evidence_ids":["TX-或IX-编号"]}],'
    '"cited_ids":[],"missing_evidence":[]}。'
    "不要 Markdown。不要编造材料里没有的账号、金额、流水号、法规条款。"
)

# 渲染结果里不得出现的极性词与规则层 code。用边界避免误伤普通英文单词的前后缀。
LEAK_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])("
    r"polarity|annotation_reason|gold|tag|support|counter|context|"
    r"alert-trigger|alert-typology-context|structuring|funnel|night-out|layering|"
    r"watchlist|unregistered-counterparty|pattern-peer|base-risk|kb_hits"
    r")(?![A-Za-z0-9])"
)


def tier_standard_from_judge_v3() -> str:
    """只抽 judge_v3 的三档标准与一致性约束，停在引用契约之前。"""
    text = PROMPTS["judge_v3"]
    start = text.index("【三档判定标准】")
    end = text.index("【引用契约】")
    chunk = text[start:end].strip()
    spilled = ("【引用契约】", "【可执行谓词】", "allowed_evidence", "allowed_predicates")
    hit = [token for token in spilled if token in chunk]
    if hit:
        raise RuntimeError("三档标准抽取出界：" + ",".join(hit))
    return chunk


A1_SYSTEM = A0_SYSTEM + "\n" + tier_standard_from_judge_v3()


def render_leaks(text: str) -> list[str]:
    found = [m.group(0) for m in LEAK_RE.finditer(text or "")]
    if "金标" in (text or ""):
        found.append("金标")
    return found


def _money(value) -> str:
    if value is None or value == "":
        return ""
    return f"{value} 元"


def render_case(case: dict) -> str:
    vig = case.get("vignette") or {}
    customer = vig.get("customer") or {}
    alert = vig.get("alert") or {}
    lines: list[str] = ["客户"]
    for label, key in (
        ("客户号", "id"),
        ("姓名", "name"),
        ("类型", "kind"),
        ("行业", "industry"),
        ("开户时间", "opened_at"),
        ("KYC", "kyc_level"),
        ("概况", "summary"),
    ):
        val = customer.get(key)
        if val not in (None, ""):
            lines.append(f"- {label}：{val}")
    if customer.get("id_number"):
        lines.append(f"- 身份证件号：{customer['id_number']}")
    if customer.get("phone"):
        lines.append(f"- 手机号：{customer['phone']}")

    lines.append("")
    lines.append("告警")
    for label, key in (
        ("告警号", "id"),
        ("类型", "alert_type"),
        ("账号", "account_id"),
        ("客户号", "customer_id"),
        ("金额", "amount"),
        ("时间", "created_at"),
    ):
        val = alert.get(key)
        if val in (None, ""):
            continue
        if key == "amount":
            val = _money(val)
        lines.append(f"- {label}：{val}")
    summary = vig.get("summary") or ""
    if not summary:
        for finding in vig.get("findings") or []:
            if finding.get("code") == "alert-brief":
                summary = finding.get("detail") or ""
                break
    if summary:
        lines.append(f"- 说明：{summary}")

    lines.append("")
    lines.append("流水")
    txs = list(vig.get("transactions") or [])
    if not txs:
        lines.append("（无）")
    for index, tx in enumerate(txs, start=1):
        lines.append(
            f"{index}. {tx.get('id') or ''} 时间 {tx.get('occurred_at') or ''} "
            f"金额 {_money(tx.get('amount'))} 渠道 {tx.get('channel') or ''} "
            f"付款账号 {tx.get('from_account') or ''} 收款账号 {tx.get('to_account') or ''} "
            f"备注 {tx.get('remark') or ''}".rstrip()
        )

    lines.append("")
    lines.append("调查记录")
    notes = [f for f in (vig.get("findings") or []) if f.get("code") == "case-note"]
    if not notes:
        lines.append("（无）")
    for note in notes:
        ids = [str(x) for x in (note.get("evidence_ids") or []) if str(x)]
        prefix = " ".join(ids)
        detail = note.get("detail") or ""
        if prefix:
            lines.append(f"- {prefix}：{detail}")
        else:
            lines.append(f"- {detail}")

    lines.append("")
    lines.append("同业基线")
    lines.append(_render_baseline(vig.get("baseline") or {}))

    suffix = str(case.get("user_suffix") or "").strip()
    if suffix:
        lines.append("")
        lines.append("补充要求")
        lines.append(suffix)
    return "\n".join(lines).strip() + "\n"


def _render_baseline(baseline: dict) -> str:
    return (
        f"行业：{baseline.get('industry') or ''}\n"
        f"窗口流入 {baseline.get('sample_in_count')} 笔，合计 {_money(baseline.get('sample_in_sum'))}；"
        f"流出 {baseline.get('sample_out_count')} 笔，合计 {_money(baseline.get('sample_out_sum'))}；"
        f"流入笔均 {_money(baseline.get('avg_in_ticket'))}。\n"
        f"同业月流入典型值 {_money(baseline.get('peer_typical_monthly_in'))}，"
        f"同业单笔典型值 {_money(baseline.get('peer_typical_ticket'))}，"
        f"本案流入相对同业倍数 {baseline.get('in_sum_vs_peer')}。\n"
        f"同业说明：{baseline.get('peer_note') or ''}"
    )


def generic_messages(case: dict, arm: str) -> list[dict]:
    if arm not in {"A0", "A1", "B"}:
        raise ValueError(f"通用渲染只用于 A0/A1/B，收到 {arm}")
    system = A0_SYSTEM if arm == "A0" else A1_SYSTEM
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": render_case(case)},
    ]
