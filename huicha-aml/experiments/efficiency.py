"""调查效率：Human vs Human+循证慧查。

记录 Investigation Time / Evidence Missing / Wrong Judgment / Report Completeness。
没有真人对照实验时禁止填写提升百分比。
"""

from __future__ import annotations

import json

SCHEMA = {
    "investigator_id": "string",
    "case_id": "string",
    "condition": "human_only | human_plus_huicha",
    "investigation_time_sec": "number",
    "evidence_missing": "number",
    "wrong_judgment": "0|1",
    "report_completeness": "0-1",
    "data_note": "synthetic or study",
}


def main() -> dict:
    out = {
        "status": "TODO",
        "schema": SCHEMA,
        "human_investigation": "Not evaluated yet",
        "human_plus_huicha": "Not evaluated yet",
        "time_reduction": "Not evaluated yet",
        "note": "未做真人对照，不要写效率提升 80%。",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    main()
