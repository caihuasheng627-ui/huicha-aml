"""竞赛原型边界：CORS、可选演示口令、调查员登录会话。不是银行 SSO。"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Header, HTTPException, Request

# 演示账号：工号 + 口令。竞赛原型，明文即可。界面只显示岗位，不使用具体人名。
DEMO_USERS: dict[str, dict[str, str]] = {
    "002183": {"password": "aml123", "name": "调查员", "role": "反洗钱调查员"},
    "002201": {"password": "aml123", "name": "复核岗", "role": "合规复核"},
}

# token -> {staff_id, name, role, exp}
_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSION_TTL_SEC = 12 * 60 * 60


@dataclass(frozen=True)
class AuthUser:
    staff_id: str
    name: str
    role: str

    def label(self) -> str:
        return f"{self.name}（{self.staff_id}）"

    def as_dict(self) -> dict[str, str]:
        return {"staff_id": self.staff_id, "name": self.name, "role": self.role}


def cors_origins() -> list[str]:
    raw = os.getenv(
        "HUICHA_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173",
    )
    return [x.strip() for x in raw.split(",") if x.strip()]


def demo_token() -> str:
    return os.getenv("HUICHA_DEMO_TOKEN", "").strip()


def auth_mode() -> str:
    return "demo_token" if demo_token() else "off"


def require_demo_token(x_huicha_token: str | None = Header(default=None, alias="X-Huicha-Token")) -> None:
    expected = demo_token()
    if not expected:
        return
    if (x_huicha_token or "") != expected:
        raise HTTPException(401, "需要演示口令（Header X-Huicha-Token）。竞赛原型，不是银行 SSO。")


def list_demo_accounts() -> list[dict[str, str]]:
    return [
        {"staff_id": sid, "name": u["name"], "role": u["role"]}
        for sid, u in DEMO_USERS.items()
    ]


def _purge_expired() -> None:
    now = time.time()
    dead = [k for k, v in _SESSIONS.items() if float(v.get("exp") or 0) < now]
    for k in dead:
        _SESSIONS.pop(k, None)


def create_session(staff_id: str, password: str) -> tuple[str, AuthUser]:
    user = DEMO_USERS.get(staff_id.strip())
    if not user or user["password"] != password:
        raise HTTPException(401, "工号或口令不正确")
    _purge_expired()
    token = secrets.token_urlsafe(24)
    auth = AuthUser(staff_id=staff_id.strip(), name=user["name"], role=user["role"])
    _SESSIONS[token] = {
        **auth.as_dict(),
        "exp": time.time() + _SESSION_TTL_SEC,
    }
    return token, auth


def destroy_session(token: str | None) -> None:
    if token:
        _SESSIONS.pop(token, None)


def resolve_session(token: str | None) -> AuthUser | None:
    if not token:
        return None
    _purge_expired()
    row = _SESSIONS.get(token)
    if not row:
        return None
    return AuthUser(staff_id=row["staff_id"], name=row["name"], role=row["role"])


def session_from_request(request: Request) -> AuthUser | None:
    token = request.headers.get("x-huicha-session") or ""
    if not token:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    return resolve_session(token)


def require_user(request: Request) -> AuthUser:
    user = session_from_request(request)
    if not user:
        raise HTTPException(401, "请先登录后再签发或导出")
    return user
