"""结构盲区 hold-out：禁词与盲区集相同，但流水不触发规则层结构码。

目标：上报信号只落在叙事项与对手关系上，用来测 Judge 是否依赖
`structuring` / `funnel` / `night-out` / `layering` 的规则层话术。

硬约束（生成后由测试断言）：
- 叙事可控字段不含 JUDGE_V3_EXEMPLARS
- rule_finding_codes 只能是 alert-trigger（可另有 case-note / alert-brief，它们不算规则层）
- 企业案流入对手 < 4；无人账落在 4.5–5 万带且笔数 ≥ 8；无 21:00–05:59 流出
- 告警类型含「大额」或「频繁」，不含「拆分 / 归集 / 多层」
"""

from __future__ import annotations

from blind_families import JUDGE_V3_EXEMPLARS
from build_independent_set import _acc, _jitter, _ts, _tx

STRUCT_FORBIDDEN_RULES = ("structuring", "funnel", "night-out", "layering")


def _day_hour(rng, lo: int = 9, hi: int = 18) -> int:
    return rng.randint(lo, hi)


def _txs_simple_in(rng, c, ctx, src_label: str, remark: str):
    total = ctx["amount"] * 10000
    src = _acc(rng)
    ctx["labels"][src] = src_label
    txs = [_tx(src, c, total, _ts(ctx["day"], _day_hour(rng, 10, 15), rng.randint(0, 59)), "转账", remark)]
    return txs, ctx["amount"], 1


def _txs_simple_out(rng, c, ctx, dst_label: str, remark: str):
    total = ctx["amount"] * 10000
    src = _acc(rng)
    ctx["labels"][src] = "日常往来户"
    dst = _acc(rng)
    ctx["labels"][dst] = dst_label
    hour = _day_hour(rng, 10, 14)
    txs = [
        _tx(src, c, _jitter(rng, total * 0.15, 0.05), _ts(ctx["day"], hour, rng.randint(0, 20), 0, -rng.randint(4, 12)), "转账", "往来款"),
        _tx(c, dst, total, _ts(ctx["day"], hour + 2, rng.randint(0, 40)), "转账", remark),
    ]
    return txs, ctx["amount"], 1


def _txs_in_then_out(rng, c, ctx, src_label: str, dst_label: str, in_remark: str, out_remark: str):
    total = ctx["amount"] * 10000
    src, dst = _acc(rng), _acc(rng)
    ctx["labels"][src] = src_label
    ctx["labels"][dst] = dst_label
    hour = _day_hour(rng, 10, 14)
    txs = [
        _tx(src, c, total, _ts(ctx["day"], hour, rng.randint(0, 20)), "转账", in_remark),
        _tx(c, dst, _jitter(rng, total * 0.96, 0.02), _ts(ctx["day"], hour + 3, rng.randint(0, 30)), "转账", out_remark),
    ]
    return txs, ctx["amount"], 1


def _txs_tuition_refund(rng, c, ctx):
    return _txs_simple_in(rng, c, ctx, "学校财务专户", f"学费退回 学籍{rng.randint(2026001, 2026999)}")


def _txs_dividend(rng, c, ctx):
    return _txs_simple_in(rng, c, ctx, "上市公司派息户", f"分红 公告{rng.randint(1000, 9999)}")


def _txs_medical_pool(rng, c, ctx):
    return _txs_simple_in(rng, c, ctx, "单位互助医疗专户", "医疗互助报销")


def _txs_land_rent(rng, c, ctx):
    return _txs_simple_in(rng, c, ctx, "村集体结算户", f"土地租金 决议{rng.randint(20, 99)}")


def _txs_kin_gift(rng, c, ctx):
    return _txs_simple_in(rng, c, ctx, "个人账户", "转账")


def _txs_vehicle_pay(rng, c, ctx):
    return _txs_simple_out(rng, c, ctx, "二手车商户", "购车款")


def _txs_ubo_twins(rng, c, ctx):
    return _txs_in_then_out(
        rng, c, ctx,
        "同一受益所有人控制的空壳企业甲",
        "同一受益所有人控制的空壳企业乙",
        "往来款",
        "往来款",
    )


def _txs_mule_lend(rng, c, ctx):
    return _txs_in_then_out(rng, c, ctx, "客户不认识的个人户", "客户不认识的个人户", "转账", "转账")


def _txs_hawala(rng, c, ctx):
    return _txs_in_then_out(rng, c, ctx, "上游客户", "地下汇兑摊位", "货款", "货款")


def _txs_fake_project(rng, c, ctx):
    return _txs_simple_out(rng, c, ctx, "与客户亲属同址的新设企业", "工程款")


def _txs_reused_voucher(rng, c, ctx):
    return _txs_simple_out(rng, c, ctx, "与另一对手共用同一收据号的企业", "货款")


STRUCT_FAMILIES: list[dict] = [
    {
        "tag": "tuition_refund",
        "gold": "exclude",
        "alert_type": "大额学费退回",
        "industry": "教育培训",
        "kind": "individual",
        "amounts": [8, 12, 16, 22, 28],
        "reason": "学校财务专户退回未就读学期学费，学籍变动通知与金额勾稽。",
        "tx_builder": _txs_tuition_refund,
        "customer_summary": "个人客户，近期办理退学或转学，账户以生活收支为主。",
        "name_suffixes": ["有限公司"],
        "key_pool": [
            {"text": "来款对手为学校财务专户，学籍变动通知载明应退金额与到账一致", "polarity": "counter"},
            {"text": "教务系统可核该生已办结退学，退费批次号可查", "polarity": "counter"},
            {"text": "到账后未再拆转，余额留作生活备用", "polarity": "counter"},
        ],
        "distractor_pool": [
            {"text": "当日另有一笔小额生活缴费", "polarity": "context"},
            {"text": "短信含「退费」字样，实为培训机构营销文案", "polarity": "support"},
        ],
        "summaries": [
            "个人账户于{day}收到学校财务专户 {amount} 万元，附学籍变动通知。",
            "退学退费 {amount} 万到账，教务批次可核。",
            "{day} 到账 {amount} 万，户名与在册学生一致。",
            "学费退回 {amount} 万，应退金额与通知勾稽。",
            "学校专户转入 {amount} 万元，备注填写学费退回。",
            "单笔 {amount} 万入账后未再拆转，客户称已办退学。",
            "退费 {amount} 万与通知载明金额一致，时间为{day}。",
            "账户收入 {amount} 万，对手为学校财务专户。",
        ],
    },
    {
        "tag": "listed_dividend",
        "gold": "exclude",
        "alert_type": "大额分红入账",
        "industry": "个人-教师",
        "kind": "individual",
        "amounts": [6, 9, 14, 21, 32],
        "reason": "来款为上市公司派息户，公告文号与持股数量勾稽。",
        "tx_builder": _txs_dividend,
        "customer_summary": "教师个人客户，账户以薪酬与少量持股分红为主。",
        "key_pool": [
            {"text": "对手为上市公司派息户，分红公告文号与持股数量勾稽", "polarity": "counter"},
            {"text": "证券账户持股变动可在登记公司查询，金额一致", "polarity": "counter"},
            {"text": "到账后无大额拆转，符合派息后留存习惯", "polarity": "counter"},
        ],
        "distractor_pool": [
            {"text": "客户当日另有一笔水电代扣", "polarity": "context"},
            {"text": "备注曾写「往来」，后更正为分红", "polarity": "support"},
        ],
        "summaries": [
            "教师账户于{day}收到派息户 {amount} 万元。",
            "分红入账 {amount} 万，公告文号可核。",
            "{day} 派息 {amount} 万到账，与持股数量一致。",
            "登记公司可查持股，到账 {amount} 万。",
            "派息户转入 {amount} 万后余额留存。",
            "公告批次到账 {amount} 万元，对手为派息户。",
            "入账 {amount} 万且附公告摘录，无短时拆转。",
            "分红来款 {amount} 万，时间{day}，与除权日吻合。",
        ],
    },
    {
        "tag": "medical_pool",
        "gold": "exclude",
        "alert_type": "大额医疗互助入账",
        "industry": "个人-医护",
        "kind": "individual",
        "amounts": [5, 8, 12, 18, 24],
        "reason": "单位互助医疗专户拨付，报销清单与就诊记录勾稽。",
        "tx_builder": _txs_medical_pool,
        "customer_summary": "医护个人客户，账户以薪酬与单位互助报销为主。",
        "key_pool": [
            {"text": "来款为单位互助医疗专户，报销清单与就诊记录勾稽", "polarity": "counter"},
            {"text": "人事备案显示客户在册，互助章程覆盖该病种", "polarity": "counter"},
            {"text": "到账后 72 小时内无大额拆转", "polarity": "counter"},
        ],
        "distractor_pool": [
            {"text": "当日另有一笔药店刷卡", "polarity": "context"},
            {"text": "短信含「理赔」字样，实为互助社群推送", "polarity": "support"},
        ],
        "summaries": [
            "医护账户于{day}收到单位互助专户 {amount} 万元。",
            "互助报销 {amount} 万入账，清单与就诊记录勾稽。",
            "{day} 互助拨付 {amount} 万，人事在册可核。",
            "专户转入 {amount} 万，病种在章程覆盖范围内。",
            "报销到账 {amount} 万后未即时拆转。",
            "互助批次 {amount} 万元，对手为单位专户。",
            "入账 {amount} 万且附报销清单，无短时拆转。",
            "互助来款 {amount} 万，时间{day}，与出院日吻合。",
        ],
    },
    {
        "tag": "land_rent",
        "gold": "exclude",
        "alert_type": "大额地租入账",
        "industry": "种植合作社",
        "kind": "enterprise",
        "amounts": [18, 26, 35, 48, 62],
        "reason": "村集体结算户拨付土地租金，决议金额与到账勾稽。",
        "tx_builder": _txs_land_rent,
        "customer_summary": "种植合作社客户，账户用于农产品销售与地租收付。",
        "name_suffixes": ["种植专业合作社", "养殖专业合作社"],
        "key_pool": [
            {"text": "来款为村集体结算户，村民代表大会决议金额与到账一致", "polarity": "counter"},
            {"text": "土地承包经营权证载明面积与租金单价可勾稽", "polarity": "counter"},
            {"text": "到账后按农资采购计划留存，无即时拆转", "polarity": "counter"},
        ],
        "distractor_pool": [
            {"text": "次日有一笔农资店小额支出", "polarity": "context"},
            {"text": "会计曾把备注写成借款，次日更正为地租", "polarity": "support"},
        ],
        "summaries": [
            "合作社账户于{day}收到村集体结算户 {amount} 万元地租。",
            "地租 {amount} 万入账，决议文号可核。",
            "{day} 租金批次 {amount} 万到账，与经营权证面积勾稽。",
            "村集体拨付 {amount} 万，户名与承包方一致。",
            "租金 {amount} 万留存用于农资采购。",
            "决议对应款项 {amount} 万元，对手为村集体结算户。",
            "入账 {amount} 万且附决议摘录，无短时拆转。",
            "地租来款 {amount} 万，时间{day}，与秋收结算节点吻合。",
        ],
    },
    {
        "tag": "kin_gift_gap",
        "gold": "observe",
        "alert_type": "大额亲友转入待核",
        "industry": "个人-教师",
        "kind": "individual",
        "amounts": [12, 18, 26, 35],
        "reason": "亲友转入大额，亲属关系书面证明未齐，流水本身无异常节奏。",
        "tx_builder": _txs_kin_gift,
        "customer_summary": "教师个人客户，账户以薪酬入账为主。",
        "key_pool": [
            {"text": "客户称亲属赠与，但未提交户口簿或亲属关系证明", "polarity": "context"},
            {"text": "口头用途在「治丧」与「装修」之间变更", "polarity": "context"},
        ],
        "distractor_pool": [
            {"text": "月度薪酬入账稳定", "polarity": "counter"},
            {"text": "近窗未见夜间连笔拆转", "polarity": "counter"},
        ],
        "summaries": [
            "教师账户于{day}入账 {amount} 万，客户称亲属赠与，证明未交。",
            "大额转入 {amount} 万，亲属关系书面材料不齐。",
            "{day} 收到 {amount} 万，仅有口头说明。",
            "亲友相关入账 {amount} 万，受益人关系待书面补证。",
            "个人账户突增 {amount} 万，材料不足以闭合赠与链条。",
            "声称赠与到账 {amount} 万，缺完整权利证明。",
            "入账 {amount} 万后未能当场补齐亲属文书。",
            "大额资金 {amount} 万到账，赠与证明仍在收集。",
        ],
    },
    {
        "tag": "vehicle_docs_gap",
        "gold": "observe",
        "alert_type": "大额购车转出待核",
        "industry": "个人-医护",
        "kind": "individual",
        "amounts": [8, 12, 18, 26],
        "reason": "单笔购车支出，对手可查，过户登记材料未齐，无异常节奏。",
        "tx_builder": _txs_vehicle_pay,
        "customer_summary": "医护个人客户，账户以薪酬与日常消费为主。",
        "key_pool": [
            {"text": "单笔对公转出金额较大，客户只提供口头「购车」说明", "polarity": "context"},
            {"text": "对手工商存续，车辆登记证书与过户回执尚未提交", "polarity": "context"},
        ],
        "distractor_pool": [
            {"text": "客户职业为医护，月薪酬入账稳定", "polarity": "counter"},
            {"text": "近 30 日无夜间集中拆分特征", "polarity": "counter"},
        ],
        "summaries": [
            "医护账户于{day}转出 {amount} 万至车商，过户材料未齐。",
            "大额支付 {amount} 万，对手存续可查，登记证书仍在补。",
            "{day} 单笔支出 {amount} 万，仅有口头购车说明。",
            "对公转出 {amount} 万后未再连转，缺过户回执。",
            "账户转出 {amount} 万，过户手续承诺后补。",
            "大额支付 {amount} 万，受益人清楚但凭证缺口。",
            "转账 {amount} 万至车商，材料收集中。",
            "单笔 {amount} 万外转，流水未见连笔快进快出。",
        ],
    },
    {
        "tag": "ubo_twins",
        "gold": "suggest_report",
        "alert_type": "大额对公往来",
        "industry": "物流仓储",
        "kind": "enterprise",
        "amounts": [26, 35, 48, 62],
        "reason": "一进一出对手均为同一受益所有人控制的空壳，无真实仓储业务。",
        "tx_builder": _txs_ubo_twins,
        "customer_summary": "物流仓储企业客户，账户用于运费与仓储费收付。",
        "name_suffixes": ["物流有限公司", "仓储有限公司"],
        "key_pool": [
            {"text": "流入与流出对手的受益所有人为同一人，两家均无在营仓库", "polarity": "support"},
            {"text": "客户无法说明与这两家企业的真实运输对价", "polarity": "support"},
            {"text": "工商公示显示两家对手成立不足 30 日且无社保人数", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "企业称正常运费结算，未能提供运单", "polarity": "counter"},
            {"text": "开户满一年，KYC 为普通级", "polarity": "context"},
        ],
        "summaries": [
            "物流账户于{day}收一笔往来款后转出 {amount} 万，对手受益所有人相同。",
            "一进一出合计约 {amount} 万，两家对手均无在营仓库。",
            "{day} 往来款进入后数小时转出，对手新设无社保。",
            "客户说不清运输对价，金额约 {amount} 万。",
            "同一受益人控制的两家空壳对敲，金额 {amount} 万量级。",
            "无运单却完成对公往来 {amount} 万。",
            "新设对手快进快出 {amount} 万，受益所有人重合。",
            "仓储账户出现空壳对敲 {amount} 万。",
        ],
    },
    {
        "tag": "mule_lend",
        "gold": "suggest_report",
        "alert_type": "大额对私转出",
        "industry": "个人-灵活就业",
        "kind": "individual",
        "amounts": [12, 18, 26, 35],
        "reason": "客户承认出借账户，对手均称不认识。",
        "tx_builder": _txs_mule_lend,
        "customer_summary": "个人客户，灵活就业，账户以劳务收入为主。",
        "key_pool": [
            {"text": "客户承认把账户借给他人收款，本人不认识对手", "polarity": "support"},
            {"text": "流入与流出对手均为其无法指认的个人户", "polarity": "support"},
            {"text": "无法说明劳务对价或亲属关系", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "客户曾称代收房租，未能提供租约", "polarity": "counter"},
            {"text": "证件地址与常住地不一致", "polarity": "context"},
        ],
        "summaries": [
            "灵活就业账户于{day}收一笔转账后转出 {amount} 万，客户承认出借账户。",
            "个人户一进一出约 {amount} 万，对手均无法指认。",
            "{day} 代收后转出，客户称「帮朋友走账」。",
            "出借账户路径清楚，金额 {amount} 万量级。",
            "付款人关系说不清，出账指向陌生个人。",
            "客户承认出借账户，合计约 {amount} 万。",
            "无劳务对价的个人户快进快出 {amount} 万。",
            "代收后当日转出至其不认识的个人户。",
        ],
    },
    {
        "tag": "hawala_desk",
        "gold": "suggest_report",
        "alert_type": "大额跨境汇出",
        "industry": "跨境电商",
        "kind": "enterprise",
        "amounts": [18, 26, 35, 48],
        "reason": "货款转至地下汇兑摊位，无报关与平台订单对应。",
        "tx_builder": _txs_hawala,
        "customer_summary": "跨境电商企业客户，账户用于平台货款与物流费用收付。",
        "name_suffixes": ["跨境零售有限公司", "电子商务有限公司"],
        "key_pool": [
            {"text": "流出对手被支付机构标注为地下汇兑摊位", "polarity": "support"},
            {"text": "报关与物流单据缺失，平台订单无法对应到该笔汇出", "polarity": "support"},
            {"text": "客户无法说明为何不走持牌结售汇通道", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "企业称正常采购，只提供口头说明", "polarity": "counter"},
            {"text": "注册地与实际经营地不一致", "polarity": "context"},
        ],
        "summaries": [
            "跨境账户于{day}将 {amount} 万转至地下汇兑摊位。",
            "单笔跨境支出 {amount} 万，对手被标注为汇兑摊位。",
            "平台订单无法对应到该笔汇出。",
            "汇出 {amount} 万后未走持牌通道。",
            "客户说不清为何绕开结售汇，金额约 {amount} 万。",
            "无报关材料的对公转出 {amount} 万。",
            "{day} 货款改道汇兑摊位，合计 {amount} 万。",
            "电商账户出现汇兑摊位收款 {amount} 万。",
        ],
    },
    {
        "tag": "fake_project",
        "gold": "suggest_report",
        "alert_type": "大额工程款转出",
        "industry": "建筑工程",
        "kind": "enterprise",
        "amounts": [35, 48, 62, 85],
        "reason": "工程款打给与客户亲属同址的新设企业，现场无在施项目。",
        "tx_builder": _txs_fake_project,
        "customer_summary": "建筑工程企业客户，账户用于工程款收付与分包结算。",
        "name_suffixes": ["建筑工程有限公司", "建设集团有限公司"],
        "key_pool": [
            {"text": "收款方注册地址与客户亲属住址相同，成立不足 20 日", "polarity": "support"},
            {"text": "施工现场勘查无在施项目，监理日记为空", "polarity": "support"},
            {"text": "客户无法提供进度确认单或验收记录", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "企业称劳务分包，未能提供花名册", "polarity": "counter"},
            {"text": "开户满两年", "polarity": "context"},
        ],
        "summaries": [
            "施工企业于{day}向新设企业转出工程款 {amount} 万，收款方与亲属同址。",
            "工程款 {amount} 万打出，现场无在施项目。",
            "收款方成立不足 20 日，金额约 {amount} 万。",
            "监理日记为空，却支付 {amount} 万。",
            "进度确认单缺失，资金 {amount} 万量级。",
            "同址新设企业收取工程款 {amount} 万。",
            "{day} 对公转出 {amount} 万，验收记录空白。",
            "空壳分包路径清楚，金额 {amount} 万。",
        ],
    },
    {
        "tag": "reused_voucher",
        "gold": "suggest_report",
        "alert_type": "大额货款转出",
        "industry": "建材批发",
        "kind": "enterprise",
        "amounts": [26, 35, 48, 62],
        "reason": "同一收据号被用于两家无业务往来的对手，货权材料互相矛盾。",
        "tx_builder": _txs_reused_voucher,
        "customer_summary": "建材批发企业客户，账户主要用于进货与下游配送结算。",
        "name_suffixes": ["建材有限公司", "建材经销有限公司"],
        "key_pool": [
            {"text": "同一收据号出现在两家无业务往来的对手名下", "polarity": "support"},
            {"text": "仓储方书面否认该批货物对应两份收据", "polarity": "support"},
            {"text": "企业无法提供唯一货权证明", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "企业称正常进货，只提供口头说明", "polarity": "counter"},
            {"text": "开户满两年，KYC 为普通级", "polarity": "context"},
        ],
        "summaries": [
            "建材账户于{day}向供应商转出 {amount} 万，收据号与另一对手重复。",
            "货款 {amount} 万打出，仓储方否认对应两份收据。",
            "同一收据号被复用，金额约 {amount} 万。",
            "货权材料互相矛盾，资金 {amount} 万量级。",
            "无唯一货权证明的对公支出 {amount} 万。",
            "{day} 进货付款 {amount} 万，收据号冲突。",
            "两家对手共用收据号，路径清楚。",
            "批发账户出现重复收据付款 {amount} 万。",
        ],
    },
]


# 供测试与生成器复用：结构盲区必须避开的规则码。
assert not any(
    token in json_blob
    for fam in STRUCT_FAMILIES
    for token in JUDGE_V3_EXEMPLARS
    for json_blob in (
        fam["alert_type"],
        fam["industry"],
        fam["reason"],
        fam.get("customer_summary") or "",
        *(s for s in fam["summaries"]),
        *(it["text"] for it in fam["key_pool"] + fam["distractor_pool"]),
    )
), "STRUCT_FAMILIES 叙事含 judge_v3 例举词"
