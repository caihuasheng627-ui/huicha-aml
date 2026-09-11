"""Benchmark 框架：Accuracy / Precision / Recall / F1 / Macro-F1 / FPR / Evidence P/R。

当前 golden_set 与规则同源。独立 test_set 为空 → 能力指标 Not evaluated yet。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.metrics_lib import classification_report, evidence_prf  # noqa: E402


def load_split(name: str) -> dict:
    return json.loads((Path(__file__).parent / "benchmark" / name).read_text(encoding="utf-8"))


def main() -> dict:
    golden = load_split("golden_set.json")
    test = load_split("test_set.json")
    out = {
        "golden_n": len(golden.get("cases") or []),
        "test_n": len(test.get("cases") or []),
        "accuracy": "Not evaluated yet",
        "precision": "Not evaluated yet",
        "recall": "Not evaluated yet",
        "f1": "Not evaluated yet",
        "macro_f1": "Not evaluated yet",
        "false_positive_rate": "Not evaluated yet",
        "evidence_precision": "Not evaluated yet",
        "evidence_recall": "Not evaluated yet",
        "note": golden.get("caveat"),
        "test_status": test.get("status"),
        "example_api": classification_report.__name__,
        "evidence_api": evidence_prf.__name__,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    main()
