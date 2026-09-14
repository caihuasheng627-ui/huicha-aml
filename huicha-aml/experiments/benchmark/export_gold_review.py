"""导出 22 族金标复核表：只给 alert_type / 摘要模板 / 关键与干扰叙事项，不带 gold / prompt。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from blind_families import BLIND_FAMILIES  # noqa: E402
from build_independent_set import FAMILIES  # noqa: E402


def _pack(set_name: str, fam: dict) -> dict:
    return {
        "review_id": f"{set_name}:{fam['tag']}",
        "set": set_name,
        "tag": fam["tag"],
        "alert_type": fam["alert_type"],
        "industry": fam["industry"],
        "kind": fam["kind"],
        "summary_examples": list(fam["summaries"][:3]),
        "key_notes": [it["text"] for it in fam["key_pool"]],
        "distractor_notes": [it["text"] for it in fam["distractor_pool"]],
    }


def items() -> list[dict]:
    rows = [_pack("main", f) for f in FAMILIES] + [_pack("blind", f) for f in BLIND_FAMILIES]
    return rows


def render_md(rows: list[dict]) -> str:
    lines = [
        "# 金标独立复核表（盲评）",
        "",
        "请只根据告警类型、摘要样例、关键/干扰叙事项，给出三档之一：`exclude` / `observe` / `suggest_report`。",
        "**不要**查看 `gold`、prompt 正文或跑分。填入 `gold_review_labels.json` 后运行 `score_gold_review.py`。",
        "",
        "口径：排除 = 来源与去向均可闭合；观察 = 无异常节奏但缺关键材料；上报 = 有异常节奏或对手/陈述已被事实否定，且无经营生活解释。",
        "",
    ]
    for i, r in enumerate(rows, 1):
        keys = "\n".join(f"  - {t}" for t in r["key_notes"])
        dils = "\n".join(f"  - {t}" for t in r["distractor_notes"]) or "  - （无）"
        sums = "\n".join(f"  - {t}" for t in r["summary_examples"])
        lines.extend(
            [
                f"## {i}. `{r['review_id']}`",
                "",
                f"- 告警类型：{r['alert_type']}",
                f"- 行业 / 客户类型：{r['industry']} / {r['kind']}",
                "- 摘要样例：",
                sums,
                "- 关键叙事项：",
                keys,
                "- 干扰叙事项：",
                dils,
                "",
                "- 你的档位：`________________`",
                "- 是否边界（是/否）：`______`  理由：`________________`",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    rows = items()
    sheet = HERE / "gold_review_sheet.md"
    hidden = HERE / "gold_review_key.json"
    sheet.write_text(render_md(rows), encoding="utf-8")
    key = {
        "note": "仅供 score_gold_review.py 对照；复核人不应先看此文件。",
        "items": [
            {
                "review_id": f"{set_name}:{fam['tag']}",
                "tag": fam["tag"],
                "set": set_name,
                "gold": fam["gold"],
                "reason": fam["reason"],
            }
            for set_name, families in (("main", FAMILIES), ("blind", BLIND_FAMILIES))
            for fam in families
        ],
    }
    hidden.write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {sheet} n={len(rows)}")
    print(f"wrote {hidden}")


if __name__ == "__main__":
    main()
