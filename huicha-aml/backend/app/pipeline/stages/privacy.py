from __future__ import annotations

from ...privacy import PrivacyMap
from ..state import InvestigationState, StageContext


class PrivacyStage:
    name = "privacy"
    role = "Privacy"

    def run(self, state: InvestigationState, ctx: StageContext) -> None:
        privacy = PrivacyMap()
        privacy.build_from_bundle(state.bundle)
        state.privacy = privacy
