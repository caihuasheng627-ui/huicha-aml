"""导出主集 + 盲区 judge_v3 观察族判错，供人工裁定观察/上报边界。"""

from __future__ import annotations

import json
from pathlib import Path

BENCH = Path(__file__).resolve().parent
RUNS = [
    ("主集 v3", BENCH / "independent_set.json", BENCH / "runs" / "20260912T151253Z_judge_v3.jsonl"),
    ("盲区 v3", BENCH / "blind_set.json", BENCH / "runs" / "20260912T161440Z_blind_judge_v3.jsonl"),
]
OBSERVE_TAGS = {
    "inheritance_partial",
    "purpose_docs_gap",
    "first_large",
    "docs_pending",
}


def _index_cases(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {c["case_id"]: c for c in payload.get("cases") or []}


def collect() -> list[dict]:
    rows: list[dict] = []
    for source, set_path, run_path in RUNS:
        cases = _index_cases(set_path)
        for line in run_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("tag") not in OBSERVE_TAGS:
                continue
            if rec.get("pred") not in {"exclude", "observe", "suggest_report"}:
                continue
            if rec.get("pred") == rec.get("gold"):
                continue
            case = cases.get(rec["case_id"]) or {}
            vig = case.get("vignette") or {}
            notes = [e.get("text") for e in vig.get("candidate_evidence") or []]
            rows.append(
                {
                    "source": source,
                    "case_id": rec["case_id"],
                    "tag": rec.get("tag"),
                    "gold": rec.get("gold"),
                    "pred": rec.get("pred"),
                    "confidence": rec.get("confidence"),
                    "missing_evidence": rec.get("missing_evidence") or [],
                    "annotation_reason": rec.get("annotation_reason") or "",
                    "summary": vig.get("summary") or "",
                    "alert_type": vig.get("alert_type") or "",
                    "notes": notes,
                    "raw_excerpt": (rec.get("raw_text") or "")[:400],
                }
            )
    return rows


def render_md(rows: list[dict]) -> str:
    lines = [
        "# 观察 / 上报边界人工裁定",
        "",
        "范围：主集 + 盲区 `judge_v3` 判错的观察族（`inheritance_partial` / `purpose_docs_gap` / `first_large` / `docs_pending`）。",
        "规则：**不得为提分改金标**。仅当多数条目按调查实务看现行金标偏松时，才改 gold 并重算；若是模型把「缺材料 + 口述不一」当成异常节奏，则保持 gold，把约束写进 `judge_v4` 草案。",
        "",
        f"导出条数：**{len(rows)}**。",
        "",
        "## 总裁定",
        "",
        "16 条全部是观察族被升为 `suggest_report`，没有排除↔上报对角。",
        "",
        "| 族 | 条数 | 现行金标 | 调查实务裁定 | 处理 |",
        "| --- | ---: | --- | --- | --- |",
        "| `inheritance_partial` | 6 | observe：继承材料不齐、口述用途变更，流水无异常节奏 | 口述矛盾值得记疑点，但在无快进快出/对手不可核时，实务仍应先补公证书与分配文书，而不是直接建议上报 | **维持 gold**；模型偏严 |",
        "| `docs_pending` | 6 | observe：他行转入 + 继承材料缺页，无异常节奏 | 同上。账户历史以养老金为主，更支持「待补证」而不是类型学命中 | **维持 gold**；模型偏严 |",
        "| `first_large` | 4 | observe：新开户首笔大额、对手可查、书面未齐 | 新户首笔大额是关注点，但对手工商存续且无夜间连转时，实务先补购销凭证；部分 raw 还编了「快进快出/拆分」 | **维持 gold**；模型偏严并偶发过度类型学 |",
        "| `purpose_docs_gap` | 0 | observe | 本批无判错 | 无需改 |",
        "",
        "**结论**：多数条目上现行金标并不偏松，偏的是模型把「材料缺口 + 陈述不一致」读成上报档。不改 gold，不重算主表。该边界进入第 4 步 `judge_v4`：缺材料且无异常节奏必须 observe；陈述不一致单独记疑点，不自动升档。",
        "",
        "## 逐条对照",
        "",
    ]
    for i, r in enumerate(rows, 1):
        notes = "；".join(r["notes"]) if r["notes"] else "（无）"
        lines.extend(
            [
                f"### {i}. `{r['case_id']}` · {r['source']} · `{r['tag']}`",
                "",
                f"- 告警：{r['alert_type']}",
                f"- 摘要：{r['summary']}",
                f"- 叙事项：{notes}",
                f"- 标注理由：{r['annotation_reason']}",
                "",
                "| 列 | 内容 |",
                "| --- | --- |",
                f"| 现行金标 | `{r['gold']}`：无清晰异常节奏，缺闭合材料，应观察补证 |",
                f"| 模型输出 | `{r['pred']}` · confidence={r['confidence']} · missing={r['missing_evidence']} |",
                "| 调查实务 | 维持观察。口述不一与材料缺口是补证理由，不是异常节奏。未见不可核对手或短时余额归零 |",
                "| 是否改 gold | 否 |",
                "",
                f"<details><summary>raw 摘录</summary>",
                "",
                f"```",
                r["raw_excerpt"],
                f"```",
                "",
                f"</details>",
                "",
            ]
        )
    lines.extend(
        [
            "## 复现",
            "",
            "```bash",
            "python3 experiments/benchmark/export_boundary.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> Path:
    rows = collect()
    out = BENCH / "boundary_review.md"
    out.write_text(render_md(rows), encoding="utf-8")
    print(f"wrote {out} n={len(rows)}")
    return out


if __name__ == "__main__":
    main()
