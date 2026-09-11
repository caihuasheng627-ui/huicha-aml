"""竞赛原型的边界：CORS 白名单、可选演示口令。不是银行登录。"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException


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
