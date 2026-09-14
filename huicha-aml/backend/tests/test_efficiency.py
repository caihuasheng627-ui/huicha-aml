import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.efficiency import load_records, summarize


def test_empty_records_refuse_lift_percent():
    out = summarize([])
    assert out["n"] == 0
    assert out["time_reduction"] == "Not evaluated yet"
    assert "禁止" in out["note"]


def test_committed_csv_is_header_only():
    rows = load_records(ROOT / "experiments" / "efficiency_records.csv")
    assert rows == []


def test_summarize_does_not_emit_percent_even_with_rows():
    rows = [
        {
            "investigator_id": "P1",
            "case_id": "ALT-L-20260910",
            "condition": "human_only",
            "investigation_time_sec": 600,
            "evidence_missing": 2,
            "wrong_judgment": 0,
            "report_completeness": 0.5,
            "data_note": "synthetic-study",
        },
        {
            "investigator_id": "P2",
            "case_id": "ALT-L-20260910",
            "condition": "human_plus_huicha",
            "investigation_time_sec": 240,
            "evidence_missing": 1,
            "wrong_judgment": 0,
            "report_completeness": 0.9,
            "data_note": "synthetic-study",
        },
    ]
    out = summarize(rows)
    assert out["status"] == "evaluated"
    assert out["human_investigation"]["median_time_sec"] == 600
    assert out["human_plus_huicha"]["median_time_sec"] == 240
    assert isinstance(out["time_reduction"], dict)
    assert "百分比" in out["time_reduction"]["percent"]
