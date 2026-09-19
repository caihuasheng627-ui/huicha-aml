"""Agent pipeline vs direct product APIs (rule_baseline + one-shot enrich_judge).

What this is
    A contest-honesty process contrast on the same synthetic alerts:
    `POST /api/alerts/{id}/investigate?use_challenger=true` versus calling
    product `rule_baseline` / `enrich_judge` without planner tools, collector
    extras, or the Skeptic/challenger loop.

What this is not
    Not production F1, precision, recall, or investigation accuracy.
    Stub LLM + template gold must not be quoted as model quality.
    `use_challenger=false` is a *pipeline ablation* (collector tools still run);
    it is not the direct-API path tested here.

Signing gates are not loosened: the direct path records `can_sign=None` /
`signing_applicable=False` and does not persist a signable case.
"""

from __future__ import annotations

import json

import pytest

from app.database import SessionLocal
from app.path_compare import CAVEAT, compare_paths

LAYERING = "ALT-L-20260910"
CLEAN = "ALT-A-20260910"


def _compare(client, alert_id: str) -> dict:
    agent = client.post(f"/api/alerts/{alert_id}/investigate", params={"use_challenger": True})
    assert agent.status_code == 200, agent.text
    db = SessionLocal()
    try:
        return compare_paths(db, alert_id, agent_payload=agent.json())
    finally:
        db.close()


def test_layering_agent_vs_direct_records_process_and_rule_contrast(client):
    cmp = _compare(client, LAYERING)
    agent, direct, contrast = cmp["agent"], cmp["direct"], cmp["contrast"]

    assert cmp["data_note"] == "synthetic"
    assert cmp["caveat"] == CAVEAT
    assert "不是生产准确率" in cmp["caveat"]

    assert agent["entrypoint"].startswith("POST /api/alerts")
    assert agent["use_challenger"] is True
    assert agent["challenger_enabled"] is True
    assert agent["conclusion"] == "suggest_report"
    assert agent["rule_conclusion"] == "exclude"
    assert agent["can_sign"] is True
    assert agent["signing_applicable"] is True
    assert agent["reliability_stance"] == "committed"
    assert agent["tools_called"] > 0
    assert "get_alert" in agent["tool_names"]
    assert "Planner" in agent["stages"]
    assert "Skeptic" in agent["stages"]
    assert "Judge" in agent["stages"]

    assert direct["entrypoint"].startswith("rule_baseline")
    assert direct["challenger_enabled"] is False
    assert direct["rule_conclusion"] == "exclude"
    assert direct["tools_called"] == 0
    assert direct["tool_names"] == []
    assert direct["stages"] == []
    assert direct["counterfactual_performed"] is False
    assert direct["can_sign"] is None
    assert direct["signing_applicable"] is False
    assert direct["reliability_stance"] is None
    assert not direct["error"]
    assert "layering" in direct["finding_codes"]

    assert contrast["tool_traces_differ"] is True
    assert contrast["challenger_only_on_agent"] is True
    assert contrast["skeptic_only_on_agent"] is True
    assert contrast["signing_gate_only_on_agent"] is True
    assert contrast["can_sign_defined_only_on_agent"] is True
    assert contrast["agent_vs_rule_disagree"] is True
    assert contrast["agent_has_get_alert"] is True
    assert contrast["direct_has_no_planner_tools"] is True
    assert "get_alert" in contrast["agent_extra_tools"]


def test_clean_alert_still_contrasts_tools_and_gates_when_conclusions_agree(client):
    cmp = _compare(client, CLEAN)
    agent, direct, contrast = cmp["agent"], cmp["direct"], cmp["contrast"]

    assert agent["conclusion"] == "exclude"
    assert direct["rule_conclusion"] == "exclude"
    assert contrast["tool_traces_differ"] is True
    assert contrast["challenger_only_on_agent"] is True
    assert contrast["signing_gate_only_on_agent"] is True
    assert agent["tools_called"] > direct["tools_called"]
    assert agent["can_sign"] is not None
    assert direct["can_sign"] is None
    json.dumps(cmp, ensure_ascii=False)


@pytest.mark.parametrize("alert_id", [LAYERING, CLEAN, "ALT-B-20260910"])
def test_every_demo_alert_records_structured_contrast_not_just_http_ok(client, alert_id):
    cmp = _compare(client, alert_id)
    contrast = cmp["contrast"]
    assert cmp["alert_id"] == alert_id
    assert contrast["tool_traces_differ"]
    assert contrast["challenger_only_on_agent"]
    assert contrast["direct_has_no_planner_tools"]
    assert any(contrast[k] for k in ("tool_traces_differ", "agent_vs_rule_disagree", "signing_gate_only_on_agent"))
