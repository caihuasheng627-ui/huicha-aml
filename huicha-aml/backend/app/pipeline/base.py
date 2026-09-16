from __future__ import annotations

from typing import Protocol

from .state import InvestigationState, StageContext


class Stage(Protocol):
    name: str
    role: str

    def run(self, state: InvestigationState, ctx: StageContext) -> None: ...
