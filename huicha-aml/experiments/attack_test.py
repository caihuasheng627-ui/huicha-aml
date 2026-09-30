"""工具/权限攻击测试框架。Agent 不得改交易、改客户、改规则、删数据、自动上报。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.tools import ALLOWED_TOOLS  # noqa: E402

FORBIDDEN = [
    "update_transaction",
    "update_customer",
    "update_risk_rule",
    "delete_data",
    "auto_file_str",
]


def _vs_attacks() -> dict | None:
    path = Path(__file__).resolve().parent / "RESULTS.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    block = data.get("vs_generic")
    if not isinstance(block, dict) or not isinstance(block.get("attacks"), dict):
        return None
    return block["attacks"]


def _brief(metrics: dict | None) -> dict | str:
    if not isinstance(metrics, dict):
        return "Not evaluated yet"
    keys = (
        "n_cases",
        "n_scored",
        "complete",
        "inject_success_rate",
        "inject_hits",
        "inject_n",
        "bait_cite_rate",
        "bait_cite_hits",
        "blocked_rate",
        "blocked_hits",
        "regulation_match_rate",
        "regulation_matched",
        "regulation_citations",
        "regulation_uncited_rate",
        "overreach_rate",
        "high_conf_closed_rate",
        "pii_sent",
        "pii_in_chat_messages",
        "pii_in_masked_payload",
        "parse_failures",
        "api_errors",
        "privacy_gates",
    )
    return {key: metrics[key] for key in keys if key in metrics}


def main() -> dict:
    absent = {name: name not in ALLOWED_TOOLS for name in FORBIDDEN}
    out = {
        "allowed_tools": ALLOWED_TOOLS,
        "forbidden_tools_absent": absent,
        "auto_report": False,
        "attack_success_rate": "Not evaluated yet",
        "note": "白名单由代码保证；动态越权评测 TODO。",
    }
    attacks = _vs_attacks()
    if attacks:
        kinds = (
            "inject_prompt",
            "fabricate_bait",
            "fake_regulation",
            "pii_egress",
            "overreach",
            "evidence_removed",
        )
        out["vs_generic_attacks"] = {
            kind: {arm: _brief((attacks.get(kind) or {}).get(arm)) for arm in ("A1", "A3")} for kind in kinds
        }
        inject = attacks.get("inject_prompt") or {}
        if isinstance(inject.get("A1"), dict) or isinstance(inject.get("A3"), dict):
            out["attack_success_rate"] = {
                "inject_prompt_A1": _brief(inject.get("A1")),
                "inject_prompt_A3": _brief(inject.get("A3")),
            }
            out["note"] = "白名单仍由代码核对。注入成功率来自 RESULTS.json 的 vs_generic.attacks，没有另造数字。"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    main()
