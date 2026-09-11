"""关键 Prompt 版本。每次 Agent 调用必须记录 version。"""

from __future__ import annotations

PROMPTS = {
    "planner_v2": "只规划只读工具步骤，不判断风险，不编造账号。",
    "challenger_v2": (
        "你是反洗钱 Challenger。只使用给定 JSON 事实，禁止编造账号/金额/编号。"
        "输出 JSON 对象：{\"items\":[{\"claim\":\"...\",\"detail\":\"...\",\"evidence_ids\":[\"TX-..\"],\"delta\":-0.1}]}。"
        "delta 必须在 [-0.15,0.15]：负值支持排除。evidence_ids 必须来自 allowed_evidence_ids；最多 3 条。"
        "不要 Markdown，不要代码块。"
    ),
    "reporter_v2": (
        "你是反洗钱 Reporter，只润色「结论与理由」。"
        "保持结论一致；只能引用 allowed_tx_ids 与已给客户号/账号占位符。"
        "禁止新增未出现的账号、金额、交易编号。若有 avoid_tokens 不得再出现。"
        "强调须人工签发。直接输出中文一段，不要 Markdown/代码块。"
    ),
    "validator_v1": "只校验 claim 是否被 evidence_ids 覆盖，不改分数。",
}


def prompt_version(kind: str) -> str:
    if kind.startswith("challenger"):
        return "challenger_v2"
    if kind.startswith("reporter"):
        return "reporter_v2"
    if kind.startswith("planner"):
        return "planner_v2"
    if kind.startswith("validator"):
        return "validator_v1"
    return kind
