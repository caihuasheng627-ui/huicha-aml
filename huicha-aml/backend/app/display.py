"""工作台展示用编号。内部主键仍是 ALT-/6222- 形态，供回查与引用。"""

from __future__ import annotations


def case_no(alert_id: str, created_at: str = "") -> str:
    """ALT-B-20260910 → 20260910-B。"""
    parts = str(alert_id or "").split("-")
    if len(parts) >= 3 and parts[0] == "ALT":
        return f"{parts[-1]}-{parts[1]}"
    date = str(created_at or "")[:10].replace("-", "")
    return date or str(alert_id or "")


def mask_account(acct: str) -> str:
    s = str(acct or "")
    if s.startswith("6222") and len(s) >= 8:
        return f"{s[:4]}****{s[-4:]}"
    return s


def display_name(name: str) -> str:
    text = str(name or "")
    return (
        text.replace("（演示）", "")
        .replace("（合成）", "")
        .replace("演示", "")
        .strip()
        or text
    )
