from .analyst import AnalystStage
from .assemble import AssembleStage
from .collector import CollectorStage
from .guardrail import GuardrailStage
from .judge import JudgeStage
from .planner import PlannerStage
from .privacy import PrivacyStage
from .reporter import ReporterStage
from .skeptic import SkepticStage

STAGES = [
    PlannerStage(),
    CollectorStage(),
    PrivacyStage(),
    AnalystStage(),
    JudgeStage(),
    SkepticStage(),
    ReporterStage(),
    GuardrailStage(),
    AssembleStage(),
]
