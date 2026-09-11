"""一键跑通 V2 Demo：A→B→C→D 多层转移（合成数据）。

用法（在 backend 目录）：
  python -m app.demo
"""

from __future__ import annotations

import json
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from .agents import run_investigation
from .database import Base
from .seed import seed_if_empty


def _stub_chat(messages, *, temperature=0.0, max_tokens=900):
    usage = {"prompt_tokens": 8, "completion_tokens": 16, "total_tokens": 24, "cached": False, "model": "stub"}
    sys = messages[0]["content"]
    user = messages[-1]["content"]
    if "Challenger" in sys or "质疑" in sys or "delta" in sys:
        try:
            data = json.loads(user)
            eids = (data.get("allowed_evidence_ids") or ["TX-L-01"])[:2]
        except Exception:
            eids = ["TX-L-01"]
        payload = {
            "items": [
                {
                    "claim": "或为正常过桥结算",
                    "detail": "时间窗短但金额递减，需核验合同。合成反证。",
                    "evidence_ids": eids,
                    "delta": -0.10,
                }
            ]
        }
        return json.dumps(payload, ensure_ascii=False), usage
    data = json.loads(user)
    text = (
        f"结论为{data['conclusion']}。相关交易编号：{data['allowed_tx_ids']}。"
        "须人工签发，不可自动报送。"
    )
    return text, usage


def run_demo(alert_id: str = "ALT-L-20260910") -> dict:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    seed_if_empty(db)
    os.environ.setdefault("DASHSCOPE_API_KEY", "sk-demo-stub")
    import app.llm as llm_mod

    llm_mod._ENV_LOADED = False
    llm_mod.chat = _stub_chat  # type: ignore
    result = run_investigation(db, alert_id, use_challenger=True)
    db.close()
    return {
        "case_id": alert_id,
        "data_note": result.get("data_note"),
        "plan": result.get("investigation_plan"),
        "timeline": result.get("timeline"),
        "risk": result.get("risk"),
        "counterfactual": result.get("counterfactual"),
        "recommendation": (result.get("case_v2") or {}).get("recommendation"),
        "human_required": True,
        "steps": [s.get("role") for s in result.get("steps") or []],
        "note": "AI 建议不是监管结论，须人工签发后才能进入报送。",
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))
