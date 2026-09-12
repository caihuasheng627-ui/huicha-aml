"""对照 gold_review_labels.json 与 gold_review_key.json，计算一致率，并按 clear/boundary 重切已有跑分。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.metrics_lib import LABELS, classification_report  # noqa: E402

RUNS = {
    "main_judge_v3": BENCH / "runs" / "20260912T151253Z_judge_v3.jsonl",
    "blind_judge_v3": BENCH / "runs" / "20260912T161440Z_blind_judge_v3.jsonl",
    "main_judge_v2": BENCH / "runs" / "20260912T144147Z_judge_v2.jsonl",
    "blind_judge_v2": BENCH / "runs" / "20260912T165213Z_blind_judge_v2.jsonl",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def score_labels(labels: dict, key: dict) -> dict:
    key_map = {it["review_id"]: it for it in key["items"]}
    reviews = labels.get("reviews") or []
    agree = 0
    rows = []
    for rev in reviews:
        rid = rev["review_id"]
        gold = (key_map.get(rid) or {}).get("gold")
        pred = rev.get("label")
        boundary = bool(rev.get("boundary"))
        match = pred == gold
        agree += int(match)
        if not match:
            boundary = True
        rows.append(
            {
                "review_id": rid,
                "tag": (key_map.get(rid) or {}).get("tag"),
                "set": (key_map.get(rid) or {}).get("set"),
                "gold": gold,
                "reviewer": pred,
                "agree": match,
                "boundary": boundary,
                "note": rev.get("note") or "",
            }
        )
    n = len(rows)
    boundary_tags = {r["tag"] for r in rows if r["boundary"]}
    return {
        "reviewer": labels.get("reviewer"),
        "reviewer_role": labels.get("reviewer_role"),
        "n": n,
        "agree_n": agree,
        "agreement": round(agree / n, 4) if n else None,
        "boundary_families": sorted(boundary_tags),
        "clear_families": sorted({r["tag"] for r in rows if not r["boundary"]}),
        "rows": rows,
        "honesty": labels.get("honesty") or "",
    }


def _split_run(path: Path, boundary_tags: set[str]) -> dict:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    scored = [r for r in rows if r.get("pred") in LABELS]
    buckets = {
        "all": scored,
        "clear": [r for r in scored if r.get("tag") not in boundary_tags],
        "boundary": [r for r in scored if r.get("tag") in boundary_tags],
    }
    out = {}
    for name, items in buckets.items():
        y_true = [r["gold"] for r in items]
        y_pred = [r["pred"] for r in items]
        rep = classification_report(y_true, y_pred) if items else classification_report([], [])
        per = rep.get("per_class") or {}
        present = [per[lab]["f1"] for lab in LABELS if (per.get(lab) or {}).get("support")]
        out[name] = {
            "n": len(items),
            "macro_f1": rep.get("macro_f1"),
            "macro_f1_present": round(sum(present) / len(present), 4) if present else None,
            "accuracy": rep.get("accuracy"),
            "label_dist": rep.get("label_dist"),
            "per_class": per,
        }
    return out


def main() -> dict:
    labels = _load_json(BENCH / "gold_review_labels.json")
    key = _load_json(BENCH / "gold_review_key.json")
    agreement = score_labels(labels, key)
    boundary_tags = set(agreement["boundary_families"])
    by_run = {name: _split_run(path, boundary_tags) for name, path in RUNS.items() if path.exists()}
    result = {
        "agreement": {k: v for k, v in agreement.items() if k != "rows"},
        "disagreements": [r for r in agreement["rows"] if not r["agree"]],
        "boundary_rows": [r for r in agreement["rows"] if r["boundary"]],
        "by_run": by_run,
        "note": (
            "clear/boundary 是按族切已有跑分，不是新的人工标注集。"
            "不一致自动标 boundary；复核人也可主动标 boundary。"
        ),
    }
    out = BENCH / "gold_review_score.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
