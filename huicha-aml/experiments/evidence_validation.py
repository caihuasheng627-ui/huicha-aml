"""Evidence Validator 实验框架。"""

from __future__ import annotations

import json
from pathlib import Path


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


def main() -> dict:
    out = {
        "status": "TODO",
        "checks": [
            "evidence exists",
            "evidence belongs to case",
            "evidence supports claim",
            "no permission bypass",
        ],
        "evidence_validity": "Not evaluated yet",
        "blocked_invalid_claim_rate": "Not evaluated yet",
    }
    attacks = _vs_attacks()
    if attacks:
        removed = (attacks.get("evidence_removed") or {}).get("A3")
        fabricate = (attacks.get("fabricate_bait") or {}).get("A3")
        if isinstance(removed, dict) and removed.get("citation_valid_rate") is not None:
            out["evidence_validity"] = removed["citation_valid_rate"]
            out["status"] = "from_vs_generic"
        if isinstance(fabricate, dict) and fabricate.get("blocked_rate") is not None:
            out["blocked_invalid_claim_rate"] = fabricate["blocked_rate"]
            out["status"] = "from_vs_generic"
        if out["status"] == "from_vs_generic":
            out["note"] = "数字来自 RESULTS.json 的 vs_generic.attacks，没有另造。"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    main()
