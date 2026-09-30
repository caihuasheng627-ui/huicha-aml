"""用修好的事实回查和合法编号，重算已有 jsonl 的编造标记、拦截和引用分母。不调模型。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

from app.tools import fact_check, hard_fact_issues  # noqa: E402
from experiments.vs_generic.run_arms import fact_payload  # noqa: E402
from experiments.vs_generic.score import case_valid_ids  # noqa: E402

RUNS = HERE / "runs"
BENCH = HERE.parent / "benchmark"


def case_index() -> dict[str, dict]:
    index: dict[str, dict] = {}
    for name in ("blind_set.json", "struct_set.json"):
        payload = json.loads((BENCH / name).read_text(encoding="utf-8"))
        for case in payload["cases"]:
            index[case["case_id"]] = case
    attack = json.loads((HERE / "attack_set.json").read_text(encoding="utf-8"))
    for item in attack["cases"]:
        index[item["case"]["case_id"]] = item["case"]
    return index


def rescore_file(path: Path, index: dict[str, dict]) -> tuple[int, int]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    changed = 0
    missing = 0
    for row in rows:
        if row.get("_meta") or not row.get("parse_ok"):
            continue
        case = index.get(row.get("case_id") or "")
        if case is None:
            missing += 1
            continue
        reasons = row.get("reasons") or []
        text = "\n".join(str(item.get("text") or "") for item in reasons if isinstance(item, dict))
        hard = hard_fact_issues(fact_check(text, fact_payload(case)))
        row["fact_hard"] = [{"token": item.get("token"), "kind": item.get("kind")} for item in hard]
        row["fact_hard_n"] = len(hard)
        row["valid_ids"] = case_valid_ids(case)
        if row.get("arm") == "A3":
            row["blocked"] = bool((row.get("verify_hard_n") or 0) or hard)
        else:
            row["blocked"] = False
        changed += 1
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return changed, missing


def main() -> None:
    index = case_index()
    for path in sorted(RUNS.glob("*.jsonl")):
        changed, missing = rescore_file(path, index)
        print(f"{path.name} rescored={changed} missing_case={missing}")


if __name__ == "__main__":
    main()
