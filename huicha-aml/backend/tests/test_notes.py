from app.notes import (
    apply_remarks_to_report,
    check_note_facts,
    compose_human_note,
    format_remarks_section,
    note_metrics,
    sanitize_note,
    split_checklist,
)


def test_compose_keeps_checklist_block():
    existing = "先记一笔\n\n【补证清单】签发前待补材料\n- 用途证明"
    out = compose_human_note(existing, "改为观察并补证")
    assert out.startswith("改为观察并补证")
    assert "【补证清单】签发前待补材料" in out
    assert "先记一笔" not in out


def test_apply_remarks_does_not_swallow_checklist():
    report = {
        "full_text": "【结论与理由】排除。须人工签发。\n【补证清单】签发前待补材料\n- 用途证明",
        "elements": [],
    }
    apply_remarks_to_report(
        report,
        "人工判断维持观察\n\n【补证清单】签发前待补材料\n- 用途证明",
        entries=[{"text": "人工判断维持观察", "at": "2026-09-17 12:00:00", "by_name": "调查员"}],
    )
    full = report["full_text"]
    assert "【结论与理由】排除" in full
    assert "【补证备注】（人工声明，未经系统回查）" in full
    assert "调查员：人工判断维持观察" in full
    assert "【补证清单】签发前待补材料" in full
    assert full.index("【补证备注】") < full.index("【补证清单】")


def test_note_fact_warnings_are_soft():
    payload = {
        "alert": {"id": "ALT-A-20260910", "account_id": "6222-A-8801", "amount": 100, "created_at": "2026-09-10"},
        "customer": {"id": "C-A", "name": "华东百货", "opened_at": "2018-01-01"},
        "transactions": [
            {
                "id": "TX-A-1",
                "amount": 100,
                "from_account": "6222-A-8801",
                "to_account": "6222-B-1",
                "occurred_at": "2026-09-09 10:00:00",
            }
        ],
        "baseline": {},
        "graph": {"nodes": []},
        "watch_hits": [],
        "kb_hits": [],
        "evidence": [],
    }
    warnings = check_note_facts("已核对 6222-FAKE-9999", payload)
    assert any(row["token"] == "6222-FAKE-9999" for row in warnings)
    assert all(row["severity"] == "soft" for row in warnings)
    assert not check_note_facts("已核对 6222-A-8801", payload)


def test_sanitize_strips_section_marks():
    assert "【补证备注】" not in sanitize_note("见【补证备注】正文")
    free, checklist = split_checklist("意见\n【补证清单】一项")
    assert free == "意见"
    assert checklist.startswith("【补证清单】")


def test_note_metrics_count_blocked_with_note():
    class Inv:
        def __init__(self, note):
            self.human_note = note

    pairs = [
        (Inv("人工已核"), {"can_sign": False, "sign_blockers": [{"code": "fact_check", "message": "事实回查未通过"}], "human_review": {"notes": [{"text": "人工已核", "blockers": [{"code": "fact_check"}]}]}}),
        (Inv(""), {"can_sign": False, "sign_blockers": [{"code": "cf_invalid"}]}),
        (Inv("可签"), {"can_sign": True, "sign_blockers": []}),
    ]
    out = note_metrics(pairs)
    assert out["blocked_unsigned"] == 2
    assert out["blocked_with_note"] == 1
    assert out["blocked_note_rate"] == 0.5
    assert out["sign_blocker_counts"]["fact_check"] == 1
    assert out["note_by_blocker"]["fact_check"] == 1
    assert format_remarks_section([{"text": "补一句", "by_name": "调查员"}]).startswith("【补证备注】")
