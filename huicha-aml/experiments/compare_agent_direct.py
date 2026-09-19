"""Optional head-to-head: agent pipeline vs direct product APIs.

Default (CI-safe): deterministic stub LLM.
Live calls: pass `--real` or set HUICHA_COMPARE_REAL=1. Requires an API key.
Does not write Macro-F1 / accuracy; this is a process contrast on synthetic alerts.

Usage:
  python experiments/compare_agent_direct.py
  python experiments/compare_agent_direct.py --real
  python experiments/compare_agent_direct.py --alerts ALT-L-20260910 ALT-A-20260910
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base  # noqa: E402
from app.path_compare import CAVEAT, compare_paths  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402

DEFAULT_ALERTS = ["ALT-L-20260910", "ALT-A-20260910", "ALT-B-20260910"]


def _wants_real(flag: bool) -> bool:
    env = os.getenv("HUICHA_COMPARE_REAL", "").strip().lower()
    return flag or env in {"1", "true", "yes", "on"}


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    seed_if_empty(db)
    return db


def _install_stub() -> None:
    import app.llm as llm_mod

    os.environ.setdefault("DASHSCOPE_API_KEY", "sk-compare-stub")
    os.environ["HUICHA_LLM_STUB"] = "1"
    llm_mod._ENV_LOADED = False

    def _stub(messages, *, temperature=0.0, max_tokens=900, **_kwargs):
        return llm_mod._offline_stub_chat(messages)

    llm_mod.chat = _stub  # type: ignore[method-assign]


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description="Agent vs direct-API process comparison (not production F1).")
    parser.add_argument("--real", action="store_true", help="Call the configured live LLM. Requires an API key.")
    parser.add_argument("--alerts", nargs="*", default=DEFAULT_ALERTS, help="Alert ids to compare.")
    args = parser.parse_args(argv)

    real = _wants_real(args.real)
    if real:
        from app.llm import require_api_key

        require_api_key()
        os.environ.pop("HUICHA_LLM_STUB", None)
        import app.llm as llm_mod

        llm_mod._ENV_LOADED = False
    else:
        _install_stub()

    db = _session()
    rows = []
    try:
        for alert_id in args.alerts:
            rows.append(compare_paths(db, alert_id))
    finally:
        db.close()

    out = {
        "status": "ok",
        "mode": "real" if real else "stub",
        "data_note": "synthetic",
        "caveat": CAVEAT,
        "n": len(rows),
        "comparisons": rows,
        "note": (
            "live mode still uses the demo seed, not an independent labeled holdout. "
            "Do not report these rows as production accuracy."
            if real
            else "stub mode is for CI / contest honesty of the *process*, not model quality."
        ),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    main()
