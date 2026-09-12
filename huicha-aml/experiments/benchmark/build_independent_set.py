"""生成与规则模板不同源的合成独立标注集（≥200）。

叙事族来自 vignette 剧本，不是 seed_extended 的 PATTERNS 循环。
标注理由写入 annotation_reason；gold 与候选证据一并给出，供 Evidence P&R。
"""

from __future__ import annotations

import json
from pathlib import Path

# 与 backend/app/seed_extended.PATTERNS 刻意不同源的叙事族。
FAMILIES: list[dict] = [
    {
        "tag": "payroll_batch",
        "gold": "exclude",
        "reason": "对手为登记发薪通道，笔数与在册人数匹配，属常规薪酬批次。",
        "alert_type": "批量对私转出",
        "industry": "制造业",
        "support_kind": "payroll_roster",
        "noise_kind": "atm_cash",
    },
    {
        "tag": "insurance_claim",
        "gold": "exclude",
        "reason": "入账备注与保单赔付编号一致，对手为持牌险企对公账户。",
        "alert_type": "大额保险赔付入账",
        "industry": "个人-受雇",
        "support_kind": "policy_payout",
        "noise_kind": "crypto_hint",
    },
    {
        "tag": "gov_subsidy",
        "gold": "exclude",
        "reason": "资金来源为财政补贴专户，金额与公示批次一致，无二次拆转。",
        "alert_type": "财政补贴入账",
        "industry": "农业合作社",
        "support_kind": "subsidy_notice",
        "noise_kind": "night_out",
    },
    {
        "tag": "escrow_release",
        "gold": "exclude",
        "reason": "房款由监管账户按网签合同释放，买卖双方身份已核验。",
        "alert_type": "监管账户放款",
        "industry": "个人-购房",
        "support_kind": "escrow_contract",
        "noise_kind": "shell_loan",
    },
    {
        "tag": "inheritance_partial",
        "gold": "observe",
        "reason": "继承关系材料不完整，用途说明前后不一致，需补证后才能排除。",
        "alert_type": "遗产过户大额",
        "industry": "个人-继承",
        "support_kind": "partial_heir_docs",
        "noise_kind": "payroll_roster",
    },
    {
        "tag": "crowdfund_pass",
        "gold": "observe",
        "reason": "众筹入账后短期过桥至个人，平台资质与用途材料不足，宜继续观察。",
        "alert_type": "众筹归集后外转",
        "industry": "互联网服务",
        "support_kind": "crowdfund_pass",
        "noise_kind": "policy_payout",
    },
    {
        "tag": "atm_smurf",
        "gold": "suggest_report",
        "reason": "多台 ATM 连续取现后回流至新开钱包地址相关账户，节奏异常。",
        "alert_type": "ATM 连环取现回流",
        "industry": "个人-无固定职业",
        "support_kind": "atm_cash",
        "noise_kind": "subsidy_notice",
    },
    {
        "tag": "invoice_circular",
        "gold": "suggest_report",
        "reason": "开票金额与物流脱节，资金在关联壳公司间闭环流转。",
        "alert_type": "循环开票资金闭环",
        "industry": "贸易代理",
        "support_kind": "invoice_loop",
        "noise_kind": "escrow_contract",
    },
    {
        "tag": "crypto_onramp",
        "gold": "suggest_report",
        "reason": "现金存入后迅速转至虚拟资产兑换商，无经营背景解释。",
        "alert_type": "现金—虚拟资产兑换",
        "industry": "个人-无固定职业",
        "support_kind": "crypto_hint",
        "noise_kind": "payroll_roster",
    },
    {
        "tag": "nested_shell_loan",
        "gold": "suggest_report",
        "reason": "无真实放款合同的层叠借款备注，资金当日多层过桥。",
        "alert_type": "层叠借款过桥",
        "industry": "投资咨询",
        "support_kind": "shell_loan",
        "noise_kind": "escrow_contract",
    },
]


def _evidence(case_id: str, kind: str, role: str) -> dict:
    eid = f"EV-{case_id}-{kind[:3].upper()}-{role[0].upper()}"
    texts = {
        "payroll_roster": "对私批次金额与在册员工工资表合计一致",
        "policy_payout": "保单赔付书编号与入账备注一致",
        "subsidy_notice": "财政补贴公示批次与到账金额一致",
        "escrow_contract": "网签合同与监管账户放款指令一致",
        "partial_heir_docs": "继承公证书缺页，受益人关系待补",
        "crowdfund_pass": "众筹平台入账后 2 小时内转出至个人",
        "atm_cash": "同一证件短时多台 ATM 取现后回流",
        "invoice_loop": "关联公司互开增值税发票且无物流轨迹",
        "crypto_hint": "对手方标识为虚拟资产兑换商",
        "shell_loan": "借款合同要素缺失且当日多层转出",
        "night_out": "夜间小额转出至陌生个人",
    }
    return {"id": eid, "kind": kind, "text": texts.get(kind, kind)}


def build_cases(n: int = 220) -> list[dict]:
    cases = []
    for i in range(n):
        fam = FAMILIES[i % len(FAMILIES)]
        case_id = f"IND-{i + 1:04d}"
        support = _evidence(case_id, fam["support_kind"], "support")
        noise = _evidence(case_id, fam["noise_kind"], "noise")
        kyc = {
            "id": f"EV-{case_id}-KYC",
            "kind": "kyc",
            "text": f"{fam['industry']}客户 KYC 摘要（合成 vignette）",
        }
        gold_ids = [support["id"], kyc["id"]]
        if fam["gold"] == "observe":
            # 观察档：部分支持证据 + 缺失材料提示
            gold_ids = [support["id"]]
        cases.append(
            {
                "case_id": case_id,
                "gold": fam["gold"],
                "tag": fam["tag"],
                "annotation_reason": f"[{fam['tag']}] {fam['reason']}",
                "gold_evidence_ids": gold_ids,
                "vignette": {
                    "alert_type": fam["alert_type"],
                    "industry": fam["industry"],
                    "summary": (
                        f"合成 vignette #{i + 1}：告警「{fam['alert_type']}」，"
                        f"行业「{fam['industry']}」。叙事族={fam['tag']}，与规则模板不同源。"
                    ),
                    "signals": [
                        f"关键线索：{support['text']}",
                        f"干扰线索：{noise['text']}",
                        f"KYC：{kyc['text']}",
                    ],
                    "candidate_evidence": [support, noise, kyc],
                },
            }
        )
    return cases


def main() -> Path:
    out = Path(__file__).with_name("independent_set.json")
    payload = {
        "data_note": "synthetic-independent",
        "split": "independent",
        "source": "narrative_vignette_v1",
        "caveat": (
            "与 seed_extended 规则模板不同源的合成 vignette 标注集；"
            "annotation_reason 为脚本写入的标注理由，不是人工专家标注；"
            "禁止写成生产准确率。"
        ),
        "cases": build_cases(220),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out} n={len(payload['cases'])}")
    return out


if __name__ == "__main__":
    main()
