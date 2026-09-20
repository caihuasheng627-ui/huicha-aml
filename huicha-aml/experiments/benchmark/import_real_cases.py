"""把脱敏后的真实案件 CSV 转成 benchmark 可用的 real_holdout.json。

必填列：gold, alert_type, industry, customer_kind, summary
可选：case_id, amount, opened_at, customer_name, evidence（用 | 分隔叙事项）,
      tx_json（JSON 数组，字段 from_account/to_account/amount/occurred_at/channel/remark）

导入时会：
- 校验 gold 三档
- 去掉身份证号 / 手机号 / 连续 15+ 位数字
- 客户名只留姓氏 + **
- 账号改写成 ACC-****** 形态

`--placeholder` 写入 5 条手写样例，data_note=placeholder，禁止写入 RESULTS 主表。
`--public-rewrite` 写入公开典型案例改写探针，data_note=public-rewrite，同样禁止写入主表。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from io import StringIO
from pathlib import Path

HERE = Path(__file__).resolve().parent

ID_CARD_RE = re.compile(r"\b\d{17}[\dXx]\b")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
LONG_DIGIT_RE = re.compile(r"\d{15,}")
ACCOUNT_RE = re.compile(r"\b(?:ACC-)?\d{6,}\b")
GOLD = {"exclude", "observe", "suggest_report"}
KINDS = {"individual", "enterprise"}


def mask_text(text: str) -> str:
    text = ID_CARD_RE.sub("[ID]", text or "")
    text = PHONE_RE.sub("[PHONE]", text)
    text = LONG_DIGIT_RE.sub("[NUM]", text)
    return text


def mask_name(name: str, kind: str) -> str:
    name = (name or "").strip()
    if not name:
        return "某**" if kind == "individual" else "某有限公司"
    if kind == "enterprise":
        return mask_text(name)
    return name[0] + "**"


def mask_account(raw: str, salt: str) -> str:
    raw = str(raw or "")
    if raw.startswith("ACC-") and len(raw) <= 12:
        return raw
    digest = hashlib.sha1(f"{salt}:{raw}".encode("utf-8")).hexdigest()[:6].upper()
    return f"ACC-{digest}"


def _validate_row(row: dict, idx: int) -> None:
    if row.get("gold") not in GOLD:
        raise ValueError(f"row {idx}: gold 必须是 {sorted(GOLD)}")
    if row.get("customer_kind") not in KINDS:
        raise ValueError(f"row {idx}: customer_kind 必须是 {sorted(KINDS)}")
    if not (row.get("alert_type") or "").strip():
        raise ValueError(f"row {idx}: 缺少 alert_type")
    if not (row.get("industry") or "").strip():
        raise ValueError(f"row {idx}: 缺少 industry")
    if not (row.get("summary") or "").strip():
        raise ValueError(f"row {idx}: 缺少 summary")


def row_to_case(row: dict, idx: int) -> dict:
    _validate_row(row, idx)
    kind = row["customer_kind"]
    case_id = (row.get("case_id") or f"REAL-{idx:04d}").strip()
    summary = mask_text(row["summary"].strip())
    name = mask_name(row.get("customer_name") or "", kind)
    account_id = mask_account(row.get("account_id") or f"center-{idx}", case_id)
    customer_id = f"C-{idx:04d}"
    amount = float(row.get("amount") or 100000)
    opened_at = mask_text(row.get("opened_at") or "2020-01-15")
    day = "2026-06-12"
    evidence_raw = [x.strip() for x in (row.get("evidence") or "").split("|") if x.strip()]
    if not evidence_raw:
        evidence_raw = [summary]
    candidate = []
    notes = []
    for j, text in enumerate(evidence_raw, 1):
        eid = f"IX-{case_id}-{j:02d}"
        candidate.append({"id": eid, "text": mask_text(text)})
        notes.append(
            {
                "code": "case-note",
                "title": f"调查记录{j}",
                "detail": mask_text(text),
                "evidence_ids": [eid],
                "polarity": "context",
            }
        )
    txs = []
    if row.get("tx_json"):
        parsed = json.loads(row["tx_json"])
        if not isinstance(parsed, list):
            raise ValueError(f"row {idx}: tx_json 必须是数组")
        for k, t in enumerate(parsed, 1):
            txs.append(
                {
                    "id": f"TX-{case_id}-{k:02d}",
                    "from_account": mask_account(t.get("from_account") or account_id, f"{case_id}-f{k}"),
                    "to_account": mask_account(t.get("to_account") or "ACC-PEER", f"{case_id}-t{k}"),
                    "amount": float(t.get("amount") or amount),
                    "occurred_at": mask_text(str(t.get("occurred_at") or f"{day} 10:00:00")),
                    "channel": mask_text(str(t.get("channel") or "转账")),
                    "remark": mask_text(str(t.get("remark") or "转账")),
                }
            )
    else:
        txs.append(
            {
                "id": f"TX-{case_id}-01",
                "from_account": account_id,
                "to_account": "ACC-PEER1",
                "amount": amount,
                "occurred_at": f"{day} 10:30:00",
                "channel": "转账",
                "remark": "转账",
            }
        )
    alert = {
        "id": case_id,
        "alert_type": mask_text(row["alert_type"].strip()),
        "upstream": "real-holdout",
        "account_id": account_id,
        "customer_id": customer_id,
        "amount": amount,
        "created_at": f"{day} 08:30:00",
    }
    customer = {
        "id": customer_id,
        "name": name,
        "kind": kind,
        "industry": mask_text(row["industry"].strip()),
        "opened_at": opened_at,
        "kyc_level": "普通",
        "summary": mask_text(row.get("customer_summary") or summary),
    }
    findings = [
        {
            "code": "alert-brief",
            "title": "线索摘要",
            "detail": summary,
            "evidence_ids": [txs[0]["id"]],
            "polarity": "context",
        },
        {
            "code": "alert-trigger",
            "title": "上游监测命中",
            "detail": f"检测系统因「{alert['alert_type']}」生成告警。",
            "evidence_ids": [txs[0]["id"]],
            "polarity": "context",
        },
        *notes,
    ]
    allowed = sorted({t["id"] for t in txs} | {e["id"] for e in candidate} | {customer_id, account_id})
    blob = json.dumps({"alert_type": alert["alert_type"], "summary": summary, "evidence": [e["text"] for e in candidate]}, ensure_ascii=False, sort_keys=True)
    case = {
        "case_id": case_id,
        "gold": row["gold"],
        "tag": row.get("tag") or "real",
        "annotation_reason": mask_text(row.get("annotation_reason") or "真实 hold-out 导入"),
        "gold_support_ids": [e["id"] for e in candidate],
        "gold_contradict_ids": [],
        "gold_evidence_ids": [e["id"] for e in candidate],
        "rule_finding_codes": ["alert-trigger"],
        "fingerprint": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "vignette": {
            "alert_type": alert["alert_type"],
            "industry": customer["industry"],
            "summary": summary,
            "alert": alert,
            "customer": customer,
            "findings": findings,
            "transactions": txs,
            "baseline": {
                "industry": customer["industry"],
                "sample_in_count": 0,
                "sample_out_count": 1,
                "sample_in_sum": 0,
                "sample_out_sum": amount,
                "avg_in_ticket": 0,
                "peer_typical_monthly_in": 100000,
                "peer_typical_ticket": 20000,
                "peer_note": mask_text(row.get("peer_note") or "同业区间未经本行业校准"),
                "in_sum_vs_peer": None,
            },
            "graph": {"nodes": [], "edges": []},
            "kb_hits": [],
            "watch_hits": [],
            "allowed_evidence": allowed,
            "candidate_evidence": candidate,
        },
    }
    if row.get("source_url") or row.get("source_title") or row.get("source_id"):
        case["source_citation"] = {
            "id": (row.get("source_id") or "").strip(),
            "title": mask_text(row.get("source_title") or ""),
            "url": (row.get("source_url") or "").strip(),
            "public_conclusion": mask_text(row.get("public_conclusion") or ""),
        }
    if row.get("gold_provenance"):
        case["gold_provenance"] = mask_text(row["gold_provenance"])
    if row.get("ledger_note"):
        case["ledger_note"] = mask_text(row["ledger_note"])
    return case


PLACEHOLDER_CSV = """case_id,gold,alert_type,industry,customer_kind,customer_name,amount,summary,evidence,annotation_reason,tag
PH-0001,exclude,大额薪酬代发,制造业,enterprise,华辰示例公司,260000,企业向在册员工批量代发薪酬,{evidence1}|{evidence2},占位：薪酬批次可闭合,placeholder
PH-0002,observe,大额转账待核,个人-受雇,individual,李四,180000,职员账户单笔对公转出，书面用途未齐,客户仅口头说明货款|对手工商存续但书面凭证未交,占位：缺材料无异常节奏,placeholder
PH-0003,suggest_report,大额对私转出,个人-灵活就业,individual,王五,350000,客户承认出借账户后资金转出,客户承认把账户借给不认识的人|对手无法指认,占位：出借账户,placeholder
PH-0004,exclude,大额分红入账,个人-教师,individual,赵六,90000,派息户入账且公告可核,对手为派息户且公告文号可核|到账后未拆转,占位：分红可闭合,placeholder
PH-0005,observe,大额亲友转入待核,个人-教师,individual,陈七,120000,亲友转入但亲属证明未交,客户称亲属赠与但未交关系证明|月度薪酬稳定,占位：赠与待补证,placeholder
""".replace("{evidence1}", "对私合计与在册人数应发额一致").replace("{evidence2}", "发薪窗口与花名册抽检一致")


def cases_from_csv(text: str) -> list[dict]:
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV 缺少表头")
    return [row_to_case(row, i) for i, row in enumerate(reader, 1)]


DEFAULT_CAVEATS = {
    "placeholder": "真实 hold-out 槽位。placeholder 为手写样例，不是生产案件，禁止写入 RESULTS 主表，禁止写成准确率。",
    "real-imported": "真实 hold-out 导入。须为脱敏生产/从业者标注案件；禁止把未脱敏材料入库。当前拿不到生产 STR，此槽闲置；未满独立双标前禁止写成准确率。",
    "public-rewrite": (
        "公开改写探针。来源为监管通报、法院典型案例、义务机构宣传稿；"
        "gold 由作者按公开结论映射，不是独立标注；几乎全为 suggest_report，"
        "不能测排除/观察，禁止写入 RESULTS 主表，禁止写成准确率。"
    ),
}


def build_payload(
    cases: list[dict],
    *,
    data_note: str,
    source: str,
    split: str = "real_holdout",
    variant: str = "real",
    caveat: str | None = None,
    extra: dict | None = None,
) -> dict:
    raw = json.dumps(cases, ensure_ascii=False)
    if ID_CARD_RE.search(raw) or PHONE_RE.search(raw):
        raise RuntimeError("导出仍含身份证或手机号，已拒绝写入")
    payload = {
        "data_note": data_note,
        "split": split,
        "variant": variant,
        "source": source,
        "n": len(cases),
        "n_unique": len({c["fingerprint"] for c in cases}),
        "judge_input_contract": "enrich_judge(alert, customer, findings, transactions, baseline, kb_hits, allowed_evidence)；不传 missing_evidence",
        "caveat": caveat or DEFAULT_CAVEATS.get(data_note) or DEFAULT_CAVEATS["placeholder"],
        "cases": cases,
    }
    if extra:
        payload.update(extra)
    return payload


SKIP_RESULTS_NOTES = frozenset({"placeholder", "public-rewrite"})
SKIP_RESULTS_SOURCE_PREFIXES = ("real_holdout", "public_rewrite")


def skip_results_write(result: dict) -> bool:
    """placeholder / public-rewrite / 未核验真实 hold-out 不得写入 RESULTS 主表。"""
    note = str(result.get("data_note") or "")
    source = str(result.get("source") or "")
    if note in SKIP_RESULTS_NOTES:
        return True
    return any(source.startswith(prefix) for prefix in SKIP_RESULTS_SOURCE_PREFIXES)


def main(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", help="脱敏 CSV 路径")
    parser.add_argument("--placeholder", action="store_true", help="写入 5 条手写样例")
    parser.add_argument("--public-rewrite", action="store_true", help="写入公开典型案例改写探针")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    if args.placeholder:
        cases = cases_from_csv(PLACEHOLDER_CSV)
        payload = build_payload(cases, data_note="placeholder", source="real_holdout_placeholder")
        out = Path(args.out or (HERE / "real_holdout.json"))
    elif args.public_rewrite:
        from public_rewrite_cases import CAVEAT, CITATIONS, public_rewrite_rows  # noqa: WPS433

        cases = [row_to_case(row, i) for i, row in enumerate(public_rewrite_rows(), 1)]
        payload = build_payload(
            cases,
            data_note="public-rewrite",
            source="public_rewrite_holdout",
            split="public_rewrite",
            variant="public_rewrite",
            caveat=CAVEAT,
            extra={
                "gold_distribution": {"suggest_report": len(cases)},
                "selection_bias": "public cases are almost always already reported or prosecuted; always_suggest_report accuracy is 1.0 by construction; cannot measure exclude/observe",
                "citations": CITATIONS,
            },
        )
        out = Path(args.out or (HERE / "public_rewrite.json"))
    elif args.csv:
        cases = cases_from_csv(Path(args.csv).read_text(encoding="utf-8"))
        payload = build_payload(cases, data_note="real-imported", source="real_holdout")
        out = Path(args.out or (HERE / "real_holdout.json"))
    else:
        raise SystemExit("需要 --csv、--placeholder 或 --public-rewrite")
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out} n={payload['n']} data_note={payload['data_note']}")
    return out


if __name__ == "__main__":
    main()
