"""分级日志。不打印原始姓名/账号。"""

from __future__ import annotations

import logging
import re

_ACCOUNT = re.compile(r"6222-[A-Z0-9\-]+")
_COMPANY = re.compile(r"[\u4e00-\u9fff]{2,20}(?:有限公司|股份有限公司|公司)")

AUDIT = 25
logging.addLevelName(AUDIT, "AUDIT")

log = logging.getLogger("huicha")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def redact(text: str) -> str:
    out = _ACCOUNT.sub("[REDACTED]", text or "")
    return _COMPANY.sub("[REDACTED]", out)


def info(msg: str) -> None:
    log.info(redact(msg))


def warning(msg: str) -> None:
    log.warning(redact(msg))


def error(msg: str) -> None:
    log.error(redact(msg))


def audit(msg: str) -> None:
    log.log(AUDIT, redact(msg))
