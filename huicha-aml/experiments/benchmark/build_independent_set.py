"""生成与规则模板不同源的独立合成标注集（去泄漏、真组合采样）。

硬约束：
- 去重后唯一输入 ≥ 200（指纹不含 case_id）
- 输入不出现家族名、gold、关键/干扰前缀、S/N 证据后缀
- KYC 空摘要不进入 gold 证据
- annotation_reason 仅存元数据，不进模型输入
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

SEED = 20260912

# 叙事族：gold 只在元数据；summary 模板不得含标签词。
FAMILIES: list[dict] = [
    {
        "tag": "payroll_batch",
        "gold": "exclude",
        "alert_type": "批量对私转出",
        "industry": "制造业",
        "reason": "对私批次与在册工资表合计一致，属常规发薪。",
        "support_pool": [
            "对私转出合计与本月工资表人数×应发额一致",
            "发薪通道账户已在企业代发白名单登记",
            "转出时间落在固定发薪窗口，对手方均为在职员工账号",
        ],
        "noise_pool": [
            "当日另有一笔 ATM 小额取现，与发薪批次无关",
            "备注栏出现一次「借款」字样，经核对为员工备用金误填",
        ],
        "summaries": [
            "企业账户于{day}向 {n} 名员工合计转出 {amount} 万元，备注多为工资。",
            "{day} 出现批量对私支出 {amount} 万，对手方 {n} 户，集中在上午发薪窗口。",
            "代发通道单日对私 {n} 笔，合计约 {amount} 万元，户名与花名册抽检一致。",
            "制造企业账户向员工账户连发 {n} 笔，总额 {amount} 万，时间贴合发薪日。",
            "对私批量转账 {amount} 万覆盖 {n} 人，企业称月度薪酬结算。",
            "薪酬窗口内对私支出抬升至 {amount} 万，对手分散为个人账户。",
            "代发清单显示 {n} 名在职员工收款，合计 {amount} 万元。",
            "同日对私 {n} 笔小额聚合为 {amount} 万，企业说明为计件工资补发。",
        ],
    },
    {
        "tag": "insurance_claim",
        "gold": "exclude",
        "alert_type": "大额保险赔付入账",
        "industry": "个人-受雇",
        "reason": "入账与持牌险企赔付书编号一致。",
        "support_pool": [
            "对手方为持牌保险公司对公账户，入账备注含保单号",
            "赔付通知书金额与到账金额一致",
            "保单状态为已结案赔付，受益人与账户户名一致",
        ],
        "noise_pool": [
            "客户当日另有一笔小额网购支出",
            "短信通知含「兑换」字样，实为积分商城文案",
        ],
        "summaries": [
            "个人账户于{day}收到 {amount} 万元入账，对手为保险公司，备注含保单号。",
            "大额入账 {amount} 万，来源为险企对公户，客户提交赔付通知书。",
            "{day} 到账 {amount} 万，户名匹配受益人，附带结案函扫描件。",
            "保险理赔款 {amount} 万入账，保单号可在通知书核对。",
            "持牌险企转来 {amount} 万元，用途栏填写理赔。",
            "单笔 {amount} 万入账后未再外转，客户称医疗赔付到账。",
            "赔付书载明金额 {amount} 万，与流水一致，时间为{day}。",
            "账户收入 {amount} 万，对手方工商信息显示为保险股份公司。",
        ],
    },
    {
        "tag": "gov_subsidy",
        "gold": "exclude",
        "alert_type": "财政补贴入账",
        "industry": "农业合作社",
        "reason": "财政专户入账且与公示批次金额一致，无二次拆转。",
        "support_pool": [
            "资金来自财政补贴专户，批次号与县区公示一致",
            "到账后 72 小时内无大额外转",
            "合作社提供补贴项目备案表，金额勾稽相符",
        ],
        "noise_pool": [
            "夜间有一笔水电费自动扣款",
            "会计备注曾写「过桥」，后更正为「备用金划转失败冲正」",
        ],
        "summaries": [
            "合作社账户于{day}收到财政专户 {amount} 万元，对应公示批次。",
            "补贴入账 {amount} 万，来源科目为农业专项，未即时外转。",
            "{day} 财政拨款 {amount} 万到账，备案表金额一致。",
            "县区公示名单含该社，到账 {amount} 万。",
            "专户转入 {amount} 万后余额留存，用于农资采购计划。",
            "补贴批次到账 {amount} 万元，对手方为财政零余额账户。",
            "入账 {amount} 万且附带补贴说明函，无集中拆分转出。",
            "财政来款 {amount} 万，时间{day}，与项目验收节点吻合。",
        ],
    },
    {
        "tag": "escrow_release",
        "gold": "exclude",
        "alert_type": "监管账户放款",
        "industry": "个人-购房",
        "reason": "网签合同与监管账户放款指令一致。",
        "support_pool": [
            "放款指令来自住房资金监管账户",
            "网签合同买卖双方与账户户名一致",
            "放款金额与合同约定尾款一致",
        ],
        "noise_pool": [
            "放款次日有一笔物业维修基金扣款",
            "中介账户曾出现在对手方列表，金额为服务费且可解释",
        ],
        "summaries": [
            "购房人账户于{day}收到监管账户放款 {amount} 万元。",
            "尾款 {amount} 万由资金监管户划入，附网签编号。",
            "监管放款 {amount} 万，合同双方身份已核验。",
            "{day} 住房监管账户转出 {amount} 万至买方账户。",
            "按揭放款后监管户释放 {amount} 万尾款。",
            "买卖合同约定尾款 {amount} 万，当日监管户执行放款。",
            "个人账户入账 {amount} 万，来源标注住房资金监管。",
            "监管指令书金额 {amount} 万，与流水一致。",
        ],
    },
    {
        "tag": "inheritance_partial",
        "gold": "observe",
        "alert_type": "遗产过户大额",
        "industry": "个人-继承",
        "reason": "继承材料不完整，用途说明前后不一致，需补证。",
        "support_pool": [
            "客户提交部分公证书复印件，缺继承权完整页",
            "大额入账后用途说明在「治丧」与「购房」间变更",
        ],
        "noise_pool": [
            "账户历史以养老金为主，偶发亲友转入",
            "柜面曾口头称亲属关系，系统白名单未登记",
        ],
        "missing": ["完整继承公证书", "资金用途书面说明"],
        "summaries": [
            "账户于{day}入账 {amount} 万，客户称遗产分配，但公证书缺页。",
            "大额转入 {amount} 万，继承材料不齐，用途口述前后不一。",
            "{day} 收到 {amount} 万，仅有部分公证复印件。",
            "遗产相关入账 {amount} 万，受益人关系待书面补证。",
            "个人账户突增 {amount} 万，材料不足以闭合继承链条。",
            "声称遗产过户到账 {amount} 万，缺完整权利证明。",
            "入账 {amount} 万后客户未能当场补齐公证全文。",
            "大额资金 {amount} 万到账，继承与用途证明仍在收集。",
        ],
    },
    {
        "tag": "purpose_docs_gap",
        "gold": "observe",
        "alert_type": "大额转账用途待核",
        "industry": "个人-受雇",
        "reason": "单笔大额转出但合同/发票未齐，尚无清晰异常节奏，宜观察补证。",
        "support_pool": [
            "单笔对公转出金额较大，客户仅提供口头用途",
            "交易对手工商存续，但合同原件尚未提交",
        ],
        "noise_pool": [
            "客户职业为受雇职员，月工资入账稳定",
            "近 30 日无夜间集中拆分特征",
        ],
        "missing": ["购销合同原件", "发票或付款申请单"],
        "summaries": [
            "职员账户于{day}转出 {amount} 万至对公户，用途材料未齐。",
            "大额转账 {amount} 万，对手存续可查，合同仍在补。",
            "{day} 单笔支出 {amount} 万，仅有口头「货款」说明。",
            "对公转出 {amount} 万后未再连环过桥，缺书面合同。",
            "账户转出 {amount} 万，发票承诺后补，暂无其他异常节奏。",
            "大额支付 {amount} 万，受益人关系清楚但用途凭证缺口。",
            "转账 {amount} 万至贸易公司，材料收集中。",
            "单笔 {amount} 万外转，流水本身未见多层快进快出。",
        ],
    },
    {
        "tag": "atm_smurf",
        "gold": "suggest_report",
        "alert_type": "ATM 连环取现回流",
        "industry": "个人-无固定职业",
        "reason": "多台 ATM 连续取现后回流，节奏异常。",
        "support_pool": [
            "同一证件短时在多台 ATM 取现",
            "取现资金当日回流至新开个人账户",
            "回流后迅速转出，无消费或工资解释",
        ],
        "noise_pool": [
            "客户曾称「朋友周转」，未能提供书面说明",
            "开户时间短于 30 日",
        ],
        "summaries": [
            "{day} 同一证件在 {n} 台 ATM 取现后，资金回流并外转，合计约 {amount} 万。",
            "短时多点取现聚合 {amount} 万，当日回流至新账户。",
            "ATM 连环取现 {n} 笔，随后集中转入另一私户。",
            "取现合计 {amount} 万后 2 小时内回流，无经营背景。",
            "多台设备取现轨迹清晰，回流账户为新开立。",
            "现金取出再存入闭环，金额约 {amount} 万。",
            "{day} 取现—回流—外转在数小时内完成。",
            "无固定职业账户出现 ATM 聚合回流 {amount} 万。",
        ],
    },
    {
        "tag": "invoice_circular",
        "gold": "suggest_report",
        "alert_type": "循环开票资金闭环",
        "industry": "贸易代理",
        "reason": "关联公司互开票且无物流，资金闭环。",
        "support_pool": [
            "关联公司互开增值税发票，金额接近",
            "资金在关联账户间当日闭环流转",
            "物流轨迹缺失或与票面货物不符",
        ],
        "noise_pool": [
            "合同模板高度雷同，仅对手名称替换",
            "注册地址相同或相邻",
        ],
        "summaries": [
            "贸易公司于{day}与关联方互转 {amount} 万，同时互开票无物流。",
            "关联账户资金闭环 {amount} 万，票面货物无法核验。",
            "开票金额与资金流匹配但仓储记录为空。",
            "{day} 出现来回对倒 {n} 笔，合计约 {amount} 万。",
            "壳公司间循环收付 {amount} 万，缺乏真实贸易痕迹。",
            "发票与付款形成闭环，无承运单据。",
            "短时多层关联转账后余额归零，金额 {amount} 万量级。",
            "互开票后资金当日退回，疑似空转。",
        ],
    },
    {
        "tag": "crypto_onramp",
        "gold": "suggest_report",
        "alert_type": "现金—虚拟资产兑换",
        "industry": "个人-无固定职业",
        "reason": "现金存入后迅速转至兑换商。",
        "support_pool": [
            "柜面/ATM 现金存入后短时全额转出",
            "对手方标识为虚拟资产兑换商或场外承接户",
            "客户无法说明资金合法来源",
        ],
        "noise_pool": [
            "备注含「货款」但无合同",
            "开户证件地址与常住地不一致",
        ],
        "summaries": [
            "现金存入 {amount} 万后迅速转至兑换商相关账户。",
            "{day} 存现并在小时级内转出至虚拟资产通道。",
            "无固定职业账户大额存现后对接兑换商。",
            "存现—转出链条紧凑，合计约 {amount} 万。",
            "对手方名称含兑换/数字资产字样，资金来自现金。",
            "短时现金入账后清空，流向场外承接户。",
            "客户否认虚拟资产交易，但流水指向兑换商。",
            "现金来源说不清，且当日完成兑换路径。",
        ],
    },
    {
        "tag": "nested_shell_loan",
        "gold": "suggest_report",
        "alert_type": "层叠借款过桥",
        "industry": "投资咨询",
        "reason": "无真实放款合同的层叠过桥。",
        "support_pool": [
            "借款合同关键要素缺失",
            "资金当日经多层账户递减转出",
            "对手方为新设空壳或无经营流水",
        ],
        "noise_pool": [
            "备注统一填写「借款」",
            "受益所有人信息披露不全",
        ],
        "summaries": [
            "投资咨询公司于{day}收入 {amount} 万后当日多层过桥转出。",
            "层叠借款备注下资金经 {n} 个账户递减外转。",
            "无完整放款合同，却在数小时内完成过桥。",
            "新设对手方接收后迅速清空，金额约 {amount} 万。",
            "借入资金当日拆分外流，合同要素空白。",
            "过桥路径 A→B→C，耗时短，缺乏经营解释。",
            "咨询账户快进快出 {amount} 万，借款材料无法闭合。",
            "多层转账后余额接近零，指向空壳过桥。",
        ],
    },
    {
        "tag": "crowdfund_layering",
        "gold": "suggest_report",
        "alert_type": "众筹归集后短时外转",
        "industry": "互联网服务",
        "reason": "众筹归集后短时过桥至个人，具备典型分层特征。",
        "support_pool": [
            "平台入账后 2 小时内转出至个人账户",
            "归集对手分散、外转对手集中",
            "平台资质与项目材料无法核验",
        ],
        "noise_pool": [
            "对外宣传为互助项目，无备案编号",
            "入账摘要含「捐赠」但无公益许可",
        ],
        "summaries": [
            "互联网账户于{day}归集后短时外转 {amount} 万至个人。",
            "众筹入账迅速收口到单一私户，金额约 {amount} 万。",
            "分散入账、集中外转在 2 小时内完成。",
            "平台来款后立即过桥，缺乏项目兑付证明。",
            "归集—外转节奏紧凑，对手方为个人。",
            "短时资金分层路径清晰，合计 {amount} 万量级。",
            "入账标注众筹，出账无对应发放名单。",
            "归集资金当日清空至个人账户。",
        ],
    },
]


def _opaque_id(rng: random.Random, case_id: str, salt: str) -> str:
    raw = f"{case_id}:{salt}:{rng.randrange(1 << 30)}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10].upper()
    return f"EV-{digest}"


def _fingerprint(case: dict) -> str:
    vig = case["vignette"]
    blob = json.dumps(
        {
            "alert_type": vig["alert_type"],
            "industry": vig["industry"],
            "summary": vig["summary"],
            "evidence": sorted(e["text"] for e in vig["candidate_evidence"]),
            "missing": vig.get("missing_evidence") or [],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _pick_texts(rng: random.Random, pool: list[str], k_min: int, k_max: int) -> list[str]:
    k = rng.randint(k_min, min(k_max, len(pool)))
    return rng.sample(pool, k)


def build_cases(n: int = 240) -> list[dict]:
    rng = random.Random(SEED)
    cases: list[dict] = []
    seen: set[str] = set()
    attempts = 0
    i = 0
    while len(cases) < n and attempts < n * 40:
        attempts += 1
        fam = FAMILIES[i % len(FAMILIES)]
        i += 1
        case_id = f"IND-{len(cases) + 1:04d}"
        amount = rng.choice([12, 18, 26, 35, 48, 62, 85, 120, 156, 210])
        n_peer = rng.choice([3, 5, 8, 12, 17, 23])
        day = f"2026-{rng.randint(3, 9):02d}-{rng.randint(1, 28):02d}"
        summary = rng.choice(fam["summaries"]).format(amount=amount, n=n_peer, day=day)

        support_texts = _pick_texts(rng, fam["support_pool"], 1, 2)
        noise_n = rng.randint(0, 2)
        noise_texts = rng.sample(fam["noise_pool"], min(noise_n, len(fam["noise_pool"]))) if fam["noise_pool"] else []

        evidences: list[dict] = []
        gold_support: list[str] = []
        gold_contra: list[str] = []
        for idx, text in enumerate(support_texts):
            eid = _opaque_id(rng, case_id, f"sup{idx}")
            evidences.append({"id": eid, "text": text})
            gold_support.append(eid)
        for idx, text in enumerate(noise_texts):
            eid = _opaque_id(rng, case_id, f"noi{idx}")
            evidences.append({"id": eid, "text": text})
            # 噪声在 suggest_report 场景常可作为开脱/背景；exclude/observe 则多为无关
            if fam["gold"] == "suggest_report":
                gold_contra.append(eid)

        rng.shuffle(evidences)
        missing = list(fam.get("missing") or [])

        # findings 供产品 Judge：中性事实，不标注 support/counter
        findings = [
            {
                "title": f"材料摘录{j + 1}",
                "detail": ev["text"],
                "evidence_ids": [ev["id"]],
                "code": "vignette-fact",
                "polarity": "context",
            }
            for j, ev in enumerate(evidences)
        ]
        transactions = [
            {
                "id": _opaque_id(rng, case_id, f"tx{k}"),
                "amount": float(amount) * 10000 / max(1, n_peer if "批量" in fam["alert_type"] else 1),
                "occurred_at": f"{day} {10 + k}:1{k}:00",
                "from_account": f"ACC-{case_id}-A",
                "to_account": f"ACC-{case_id}-B{k}",
                "channel": "转账",
                "remark": "合成流水",
            }
            for k in range(min(3, max(1, len(evidences))))
        ]
        # 交易 ID 也进入 allowed，但不强制进 gold
        for t in transactions:
            if rng.random() < 0.35:
                evidences.append({"id": t["id"], "text": f"流水 {t['occurred_at']} 金额约 {t['amount']:.0f} 元"})

        case = {
            "case_id": case_id,
            "gold": fam["gold"],
            "tag": fam["tag"],
            "annotation_reason": f"[{fam['tag']}] {fam['reason']}",
            "gold_support_ids": gold_support,
            "gold_contradict_ids": gold_contra,
            # 兼容旧字段名：仅支持侧
            "gold_evidence_ids": list(gold_support),
            "vignette": {
                "alert_type": fam["alert_type"],
                "industry": fam["industry"],
                "summary": summary,
                "missing_evidence": missing,
                "candidate_evidence": evidences,
                "findings": findings,
                "transactions": transactions,
                "customer": {
                    "id": f"C-{case_id}",
                    "name": f"合成客户{len(cases) + 1:04d}",
                    "kind": "enterprise" if "个人" not in fam["industry"] else "individual",
                    "industry": fam["industry"],
                    "opened_at": "2024-01-15",
                    "kyc_level": "普通",
                    "summary": f"{fam['industry']}合成客户摘要",
                },
                "baseline": {"peer_note": "合成同业基线占位，非规则模板输出"},
                "kb_hits": [],
                "watch_hits": [],
            },
        }
        fp = _fingerprint(case)
        if fp in seen:
            continue
        seen.add(fp)
        case["fingerprint"] = fp
        cases.append(case)
    if len(seen) < 200:
        raise RuntimeError(f"唯一输入不足：n_unique={len(seen)} < 200")
    return cases


def main() -> Path:
    out = Path(__file__).with_name("independent_set.json")
    cases = build_cases(240)
    payload = {
        "data_note": "synthetic-independent-v2",
        "split": "independent",
        "source": "narrative_vignette_v2_combinatorial",
        "seed": SEED,
        "n": len(cases),
        "n_unique": len({c["fingerprint"] for c in cases}),
        "caveat": (
            "与 seed_extended 规则模板不同源的组合采样合成集；"
            "输入已去除家族名/关键干扰前缀/不透明证据 ID；"
            "annotation_reason 仅元数据，不进入模型上下文；"
            "不是人工专家标注；禁止写成生产准确率。"
        ),
        "cases": cases,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out} n={payload['n']} n_unique={payload['n_unique']}")
    return out


if __name__ == "__main__":
    main()
