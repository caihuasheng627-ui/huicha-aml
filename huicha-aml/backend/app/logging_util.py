"""分级日志。不打印原始姓名/账号。"""

from __future__ import annotations

import logging
import re

_PII = re.compile(r"(6222-[A-Z0-9\-]+)|([\u4e00-\u9fff]{2,12}(?:有限公司|公司)?)")

AUDIT = 25
logging.addLevelName(AUDIT, "AUDIT")

log = logging.getLogger("huicha")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def redact(text: str) -> str:
    return _PII.sub("[REDACTED]", text or "")


def info(msg: str) -> None:
    log.info(redact(msg))


def warning(msg: str) -> None:
    log.warning(redact(msg))


def error(msg: str) -> None:
    log.error(redact(msg))


def audit(msg: str) -> None:
    log.log(AUDIT, redact(msg))
