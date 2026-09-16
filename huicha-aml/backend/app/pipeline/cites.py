from __future__ import annotations

from ..schema import RegulationCite


def regulation_cites(kb_hits: list[dict], as_of: str) -> list[RegulationCite]:
    """法规依据须带转述正文与版本信息，前端展开即可核对；未命中也要留痕。"""
    cites = [
        RegulationCite(
            regulation_id=h["id"],
            title=h.get("title") or "",
            article=h.get("article") or "",
            evidence=h.get("snippet") or "",
            source=h.get("source") or "",
            as_of=as_of,
            effective_date=h.get("effective_date") or "",
            kind_label=h.get("kind_label") or "",
        )
        for h in kb_hits
        if h.get("kind") == "regulation"
    ]
    return cites or [
        RegulationCite(
            regulation_id="",
            title="未检索到足够法规依据",
            evidence="禁止编造条款",
            source="",
            as_of=as_of,
        )
    ]
