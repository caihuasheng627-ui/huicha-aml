"""调查效率：Human vs Human+循证慧查。

没有 efficiency_records.csv 中的有效样本时，拒绝输出提升百分比。
协议见 HUMAN_STUDY.md。
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

SCHEMA = {
    "investigator_id": "string",
    "case_id": "string",
    "condition": "human_only | human_plus_huicha",
    "investigation_time_sec": "number",
    "evidence_missing": "number",
    "wrong_judgment": "0|1",
    "report_completeness": "0-1",
    "data_note": "synthetic-study",
}

ALLOWED_CONDITIONS = {"human_only", "human_plus_huicha"}
RECORDS_NAME = "efficiency_records.csv"


def _records_path() -> Path:
    return Path(__file__).resolve().parent / RECORDS_NAME


def load_records(path: Path | None = None) -> list[dict]:
    target = path or _records_path()
    if not target.is_file():
        return []
    rows: list[dict] = []
    with target.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            if not raw or not any((v or "").strip() for v in raw.values()):
                continue
            condition = (raw.get("condition") or "").strip()
            if condition not in ALLOWED_CONDITIONS:
                continue
            try:
                rows.append(
                    {
                        "investigator_id": (raw.get("investigator_id") or "").strip(),
                        "case_id": (raw.get("case_id") or "").strip(),
                        "condition": condition,
                        "investigation_time_sec": float(raw["investigation_time_sec"]),
                        "evidence_missing": float(raw.get("evidence_missing") or 0),
                        "wrong_judgment": int(float(raw.get("wrong_judgment") or 0)),
                        "report_completeness": float(raw.get("report_completeness") or 0),
                        "data_note": (raw.get("data_note") or "").strip(),
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(statistics.median(values)), 2)


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {
            "status": "TODO",
            "n": 0,
            "schema": SCHEMA,
            "human_investigation": "Not evaluated yet",
            "human_plus_huicha": "Not evaluated yet",
            "time_reduction": "Not evaluated yet",
            "note": "记录表为空。按 HUMAN_STUDY.md 填入 efficiency_records.csv 之前，禁止写效率提升百分比。",
        }

    by = {name: [r for r in rows if r["condition"] == name] for name in ALLOWED_CONDITIONS}

    def arm(name: str) -> dict:
        items = by[name]
        return {
            "n": len(items),
            "median_time_sec": _median([r["investigation_time_sec"] for r in items]),
            "median_completeness": _median([r["report_completeness"] for r in items]),
            "wrong_judgment_rate": (
                round(sum(r["wrong_judgment"] for r in items) / len(items), 4) if items else None
            ),
        }

    only = arm("human_only")
    plus = arm("human_plus_huicha")
    time_reduction: str | dict
    if only["n"] and plus["n"] and only["median_time_sec"] and plus["median_time_sec"]:
        delta = only["median_time_sec"] - plus["median_time_sec"]
        time_reduction = {
            "median_sec_delta": round(delta, 2),
            "median_sec_delta_note": "only 中位数减去 plus 中位数；正值表示改稿更快",
            "percent": "Not reported — 教室对照不得外推生产，禁止把该差值写成效率提升百分比",
        }
    else:
        time_reduction = "Not evaluated yet"

    return {
        "status": "evaluated" if only["n"] and plus["n"] else "partial",
        "n": len(rows),
        "schema": SCHEMA,
        "human_investigation": only,
        "human_plus_huicha": plus,
        "time_reduction": time_reduction,
        "caveat": "synthetic-study；中位数不是生产人效；n 小时不得做显著性声明。",
        "protocol": "experiments/HUMAN_STUDY.md",
    }


def main() -> dict:
    out = summarize(load_records())
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    main()
