from __future__ import annotations

from app.sampler import SAMPLE_CAP, select_for_judge
from app.tools import alert_window


def _tx(tid, src, dst, amt, ts, channel="POS", remark="", source="subject"):
    return {
        "id": tid,
        "from_account": src,
        "to_account": dst,
        "amount": amt,
        "occurred_at": ts,
        "channel": channel,
        "remark": remark,
        "source": source,
    }


def _busy_account_txs(account_id="6222-H-7701"):
    txs = []
    for i in range(1, 121):
        txs.append(
            _tx(
                f"TX-POS-{i:03d}",
                "POS-H",
                account_id,
                1800 + i,
                f"2026-06-20 10:{(i % 50):02d}:00",
            )
        )
    for i in range(1, 9):
        txs.append(
            _tx(
                f"TX-CASH-{i:02d}",
                f"CASH-H{i:02d}",
                account_id,
                49000 + i * 50,
                f"2026-09-0{i} 09:15:00",
                "ATM/现金",
                "存入",
            )
        )
    txs.append(
        _tx("TX-NIGHT-01", account_id, "UNK-H-01", 396000, "2026-09-08 22:18:00", "网银", "转出")
    )
    for i in range(1, 5):
        txs.append(
            _tx(
                f"TX-SUP-{i:02d}",
                account_id,
                "6222-SUP",
                160000 + i * 1000,
                f"2026-07-0{i} 14:10:00",
                "对公转账",
                "采购",
            )
        )
    return txs


def test_alert_window_empty_created_at():
    assert alert_window({"created_at": ""}) == {"start": "", "end": ""}
    assert alert_window({}) == {"start": "", "end": ""}


def test_alert_window_centered_on_alert(monkeypatch):
    monkeypatch.setenv("HUICHA_TX_WINDOW_DAYS", "90")
    win = alert_window({"created_at": "2026-09-10 08:20:00"})
    assert win["start"] == "2026-06-12 08:20:00"
    assert win["end"] == "2026-09-17 08:20:00"


def test_sampler_is_deterministic_and_capped():
    txs = _busy_account_txs()
    alert = {"created_at": "2026-09-10 08:20:00", "amount": 396000, "alert_type": "拆分存入后集中转出"}
    findings = [
        {
            "code": "structuring",
            "title": "拆分",
            "evidence_ids": [f"TX-CASH-{i:02d}" for i in range(1, 9)] + ["TX-NIGHT-01"],
            "polarity": "support",
        }
    ]
    baseline = {"peer_typical_ticket": 170000}
    first = select_for_judge(alert=alert, account_id="6222-H-7701", txs=txs, findings=findings, baseline=baseline)
    second = select_for_judge(alert=alert, account_id="6222-H-7701", txs=txs, findings=findings, baseline=baseline)
    assert first == second
    assert len(first["sample"]) <= SAMPLE_CAP
    sample_ids = {t["id"] for t in first["sample"]}
    assert "TX-NIGHT-01" in sample_ids
    assert "TX-CASH-01" in sample_ids
    assert first["summary"]["total"] == len(txs)
    assert first["summary"]["sampled"] == len(first["sample"])
    assert first["summary"]["omitted"] == len(txs) - len(first["sample"])
    cluster_count = sum(c["count"] for c in first["clusters"])
    cluster_sum = round(sum(c["sum"] for c in first["clusters"]), 2)
    assert cluster_count == len(txs)
    assert cluster_sum == round(sum(t["amount"] for t in txs), 2)
    counter = [tid for tid, reasons in first["reasons"].items() if "counter_example" in reasons]
    assert len(counter) >= 2


def test_sampler_keeps_finding_reps_not_all_inflow():
    txs = _busy_account_txs()
    findings = [
        {
            "code": "funnel",
            "title": "归集",
            "evidence_ids": [t["id"] for t in txs if t["id"].startswith("TX-POS-")],
            "polarity": "support",
        }
    ]
    result = select_for_judge(
        alert={"created_at": "2026-09-10 08:20:00", "amount": 1},
        account_id="6222-H-7701",
        txs=txs,
        findings=findings,
        baseline={"peer_typical_ticket": 170000},
    )
    pos_in_sample = [t["id"] for t in result["sample"] if t["id"].startswith("TX-POS-")]
    assert "TX-POS-001" in {t["id"] for t in result["sample"]}
    assert len(pos_in_sample) < 20


def test_compact_findings_clips_to_keep_ids():
    from app.sampler import compact_findings_for_llm

    findings = [
        {
            "code": "funnel",
            "title": "归集",
            "evidence_ids": ["TX-POS-001", "TX-POS-004", "TX-CASH-01"],
            "polarity": "support",
        }
    ]
    compact = compact_findings_for_llm(findings, keep_ids={"TX-CASH-01"})
    assert compact[0]["evidence_ids"] == ["TX-CASH-01"]
    assert compact[0]["evidence_count"] == 3


def test_verify_judge_rejects_tx_outside_sample():
    from app.decision import verify_judge

    decision = {
        "disposition": "suggest_report",
        "confidence": 0.7,
        "typologies": [],
        "supporting_evidence_ids": ["TX-H-CASH-01"],
        "contradicting_evidence_ids": ["TX-H-POS-004"],
        "missing_evidence": [],
        "rationale": [{"text": "反证", "evidence_ids": ["TX-H-POS-004"]}],
        "next_actions": [],
    }
    result = verify_judge(decision, allowed_evidence={"TX-H-CASH-01", "TX-H-NIGHT-01"})
    assert result["passed"] is False
    assert "TX-H-POS-004" in result["invalid_ids"]
    assert any("进模样本或簇代表" in (i.get("message") or "") for i in result["issues"])
