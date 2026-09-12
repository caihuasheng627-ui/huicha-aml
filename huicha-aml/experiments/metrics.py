"""供仓库根目录脚本复用的指标入口。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.metrics_lib import classification_report, confusion_matrix, evidence_prf  # noqa: E402

__all__ = ["classification_report", "confusion_matrix", "evidence_prf"]
