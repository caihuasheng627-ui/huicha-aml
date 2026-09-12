"""judge_v3 例举词盲区 hold-out 族。

叙事（摘要、叙事项、备注、客户摘要、告警类型、行业说明）不得出现
JUDGE_V3_EXEMPLARS 中的词；类型学形态也与例举不同。
规则层 findings 由产品 analyze() 生成，不受此约束。
"""

from __future__ import annotations

from build_independent_set import _acc, _jitter, _ts, _tx

# 与 judge_v3「如…」例举及核心类型学词对齐；测试会扫 vignette 可控字段。
JUDGE_V3_EXEMPLARS = (
    "工资表",
    "赔付书",
    "财政批次",
    "财政",
    "监管放款",
    "监管账户",
    "网签",
    "合同",
    "公证书",
    "用途说明",
    "发票",
    "取现",
    "回流",
    "多层",
    "递减",
    "过桥",
    "关联",
    "对倒",
    "闭环",
    "现金",
    "兑换商",
    "归集",
    "集中外转",
    "阈值",
    "存入",
)


def _txs_seasonal_stock(rng, c, ctx):
    total = ctx["amount"] * 10000
    txs = []
    for k in range(3):
        buyer = _acc(rng)
        ctx["labels"][buyer] = "下游经销商"
        txs.append(_tx(buyer, c, _jitter(rng, total * 0.45), _ts(ctx["day"], rng.randint(9, 16), rng.randint(0, 59), 0, -rng.randint(5, 20)), "转账", "货款"))
    n = rng.choice([3, 4, 5])
    for k in range(n):
        sup = _acc(rng)
        ctx["labels"][sup] = "上游供应商"
        txs.append(_tx(c, sup, _jitter(rng, total / n), _ts(ctx["day"], 10 + k, rng.randint(0, 40)), "转账", "备货采购"))
    return txs, ctx["amount"], n


def _txs_equity_transfer(rng, c, ctx):
    total = ctx["amount"] * 10000
    buyer = _acc(rng)
    ctx["labels"][buyer] = "受让方企业"
    txs = [_tx(buyer, c, total, _ts(ctx["day"], rng.randint(10, 15), rng.randint(0, 59)), "转账", "股权转让价款")]
    for k in range(2):
        txs.append(_tx(_acc(rng), c, rng.randint(8000, 14000), _ts(ctx["day"], 10, rng.randint(0, 59), 0, -(30 * (k + 1))), "代发", "劳务费"))
    return txs, ctx["amount"], 1


def _txs_court_award(rng, c, ctx):
    total = ctx["amount"] * 10000
    court = _acc(rng)
    ctx["labels"][court] = "法院执行专户"
    txs = [_tx(court, c, total, _ts(ctx["day"], rng.randint(9, 14), rng.randint(0, 59)), "转账", f"执行款 案号{rng.randint(2026001, 2026999)}")]
    if rng.random() < 0.4:
        fee = _acc(rng)
        ctx["labels"][fee] = "诉讼费专户"
        txs.append(_tx(c, fee, rng.randint(2000, 8000), _ts(ctx["day"], 16, rng.randint(0, 59), 0, -rng.randint(10, 40)), "转账", "诉讼费"))
    return txs, ctx["amount"], 1


def _txs_demolition(rng, c, ctx):
    total = ctx["amount"] * 10000
    gov = _acc(rng)
    ctx["labels"][gov] = "土地储备中心"
    txs = [_tx(gov, c, total, _ts(ctx["day"], rng.randint(10, 15), rng.randint(0, 59)), "转账", "房屋征收补偿款")]
    if rng.random() < 0.5:
        bank = _acc(rng)
        ctx["labels"][bank] = "按揭银行"
        txs.append(_tx(c, bank, _jitter(rng, total * 0.15), _ts(ctx["day"], 11, rng.randint(0, 59), 0, 2), "转账", "结清按揭尾款"))
    return txs, ctx["amount"], 1


def _txs_dual_pledge(rng, c, ctx):
    """同一批货权向两家机构融资：多户转入后当日转出，触发 funnel。"""
    n = rng.randint(4, 6)
    total = ctx["amount"] * 10000
    txs = []
    hour = rng.randint(9, 11)
    for k in range(n):
        src = _acc(rng)
        ctx["labels"][src] = "个人账户"
        txs.append(_tx(src, c, _jitter(rng, total / n, 0.15), _ts(ctx["day"], hour, rng.randint(0, 50)), "转账", "放款"))
    lender = _acc(rng)
    ctx["labels"][lender] = "保理公司"
    txs.append(_tx(c, lender, total * 0.96, _ts(ctx["day"], hour + 3, rng.randint(0, 30)), "转账", "还款"))
    return txs, ctx["amount"], n


def _txs_wager_proxy(rng, c, ctx):
    n = rng.randint(5, 8)
    total = ctx["amount"] * 10000
    txs = []
    for k in range(n):
        src = _acc(rng)
        ctx["labels"][src] = "个人账户"
        txs.append(_tx(src, c, _jitter(rng, total / n, 0.25), _ts(ctx["day"], rng.randint(14, 18), rng.randint(0, 59)), "转账", "代付"))
    sink = _acc(rng)
    ctx["labels"][sink] = "个人账户"
    txs.append(_tx(c, sink, total, _ts(ctx["day"], rng.randint(21, 23), rng.randint(0, 40)), "转账", "转账"))
    return txs, ctx["amount"], n


def _txs_fx_split(rng, c, ctx):
    """接近申报线的连续流出（不用「阈值/存入」字样）。"""
    n = rng.randint(8, 10)
    txs = []
    total = 0.0
    for k in range(n):
        amt = rng.choice([49000, 49200, 49500, 49800])
        total += amt
        dst = _acc(rng)
        ctx["labels"][dst] = "境外结算户"
        txs.append(_tx(c, dst, amt, _ts(ctx["day"], 10 + k // 3, rng.randint(0, 50)), "跨境汇款", "货款"))
    src = _acc(rng)
    ctx["labels"][src] = "上游客户"
    txs.append(_tx(src, c, total, _ts(ctx["day"], 9, rng.randint(0, 20), 0, -1), "转账", "货款"))
    return txs, round(total / 10000, 1), n


def _txs_staff_pass(rng, c, ctx):
    n = rng.randint(4, 6)
    total = ctx["amount"] * 10000
    txs = []
    for k in range(n):
        corp = _acc(rng)
        ctx["labels"][corp] = "下游客户"
        txs.append(_tx(corp, c, _jitter(rng, total / n), _ts(ctx["day"], rng.randint(9, 16), rng.randint(0, 59), 0, -k), "转账", "货款"))
    boss = _acc(rng)
    ctx["labels"][boss] = "个人账户"
    txs.append(_tx(c, boss, total, _ts(ctx["day"], rng.randint(21, 22), rng.randint(0, 40)), "转账", "转账"))
    return txs, ctx["amount"], n


def _txs_shell_payroll(rng, c, ctx):
    n = rng.choice([5, 6, 7, 8])
    total = ctx["amount"] * 10000
    txs = []
    funder = _acc(rng)
    ctx["labels"][funder] = "出资方"
    txs.append(_tx(funder, c, total, _ts(ctx["day"], 9, rng.randint(0, 20)), "转账", "往来款"))
    bounced = 0.0
    for k in range(n):
        emp = _acc(rng)
        ctx["labels"][emp] = "个人账户"
        share = total / n
        txs.append(_tx(c, emp, _jitter(rng, share, 0.05), _ts(ctx["day"], 10, 10 + k * 3), "代发", "劳务费"))
        if k < 3:
            bounced += share * 0.9
            txs.append(_tx(emp, funder, share * 0.9, _ts(ctx["day"], 15, 20 + k * 4), "转账", "还款"))
    return txs, ctx["amount"], n


def _txs_first_large(rng, c, ctx):
    total = ctx["amount"] * 10000
    txs = []
    emp = _acc(rng)
    ctx["labels"][emp] = "用人单位"
    for k in range(2):
        txs.append(_tx(emp, c, rng.randint(7000, 12000), _ts(ctx["day"], 10, rng.randint(0, 59), 0, -(30 * (k + 1))), "代发", "劳务费"))
    peer = _acc(rng)
    ctx["labels"][peer] = "贸易公司"
    txs.append(_tx(c, peer, total, _ts(ctx["day"], rng.randint(11, 16), rng.randint(0, 59)), "转账", "货款"))
    return txs, ctx["amount"], 1


def _txs_docs_pending(rng, c, ctx):
    total = ctx["amount"] * 10000
    txs = []
    bank = _acc(rng)
    ctx["labels"][bank] = "他行个人户"
    txs.append(_tx(bank, c, total, _ts(ctx["day"], rng.randint(10, 15), rng.randint(0, 59)), "转账", "转账"))
    for k in range(2):
        txs.append(_tx("ACC-PENSION-02", c, rng.randint(2800, 4500), _ts(ctx["day"], 9, rng.randint(0, 40), 0, -(30 * (k + 1))), "代发", "养老金"))
    ctx["labels"]["ACC-PENSION-02"] = "社保发放账户"
    return txs, ctx["amount"], 1


BLIND_FAMILIES: list[dict] = [
    {
        "tag": "seasonal_stock",
        "gold": "exclude",
        "alert_type": "大额对公转出",
        "industry": "建材批发",
        "kind": "enterprise",
        "amounts": [35, 48, 62, 85, 120],
        "reason": "旺季备货采购与出库、进货清单勾稽，属常规经营。",
        "tx_builder": _txs_seasonal_stock,
        "key_pool": [
            {"text": "对公支出合计与本季进货清单数量×单价勾稽相符", "polarity": "counter"},
            {"text": "仓储出库记录覆盖该批采购，时间落在往年旺季窗口", "polarity": "counter"},
            {"text": "对手方均为长期合作供应商，工商存续可核", "polarity": "counter"},
        ],
        "distractor_pool": [
            {"text": "当日另有一笔水电代扣，与采购批次无关", "polarity": "context"},
            {"text": "会计曾把一笔备注写成借款，次日更正为备货采购", "polarity": "support"},
        ],
        "summaries": [
            "建材批发账户于{day}向 {n} 家供应商合计转出 {amount} 万元，企业称旺季备货。",
            "{day} 对公采购支出抬升至 {amount} 万，对手为上游供货商。",
            "单日向供应商连付 {n} 笔，合计约 {amount} 万元，时间贴合往年备货季。",
            "企业账户对公支出 {amount} 万，户名与进货清单抽检一致。",
            "备货窗口内对公付款 {amount} 万覆盖 {n} 家供应商。",
            "下游回款后集中向上游支付 {amount} 万，企业说明为季节性进货。",
            "进货清单显示 {n} 家供应商收款，合计 {amount} 万元。",
            "{day} 采购支出约 {amount} 万，出库计划与付款节奏吻合。",
        ],
    },
    {
        "tag": "equity_transfer",
        "gold": "exclude",
        "alert_type": "大额股权转让入账",
        "industry": "个人-受雇",
        "kind": "individual",
        "amounts": [48, 62, 85, 120, 156],
        "reason": "入账为股权转让价款，工商变更与价款一致。",
        "tx_builder": _txs_equity_transfer,
        "key_pool": [
            {"text": "对手方为受让企业，附工商变更受理回执，金额勾稽", "polarity": "counter"},
            {"text": "股权转让协议书（客户已交）载明价款与到账一致", "polarity": "counter"},
            {"text": "出让前后持股比例变化可在公示系统核验", "polarity": "counter"},
        ],
        "distractor_pool": [
            {"text": "客户当日另有一笔小额生活缴费", "polarity": "context"},
            {"text": "短信含「转让」字样，实为证券账户营销文案", "polarity": "support"},
        ],
        "summaries": [
            "个人账户于{day}收到 {amount} 万元，对手为受让企业，附变更回执。",
            "大额入账 {amount} 万，来源为股权价款，工商变更已受理。",
            "{day} 到账 {amount} 万，户名与出让方一致。",
            "股权价款 {amount} 万入账，公示系统可核持股变化。",
            "受让方转入 {amount} 万元，备注填写股权转让价款。",
            "单笔 {amount} 万入账后未再拆转，客户称出让持股。",
            "价款 {amount} 万与回执载明金额一致，时间为{day}。",
            "账户收入 {amount} 万，对手方工商信息显示为存续企业。",
        ],
    },
    {
        "tag": "court_award",
        "gold": "exclude",
        "alert_type": "大额法院执行入账",
        "industry": "建筑工程",
        "kind": "enterprise",
        "amounts": [35, 48, 62, 85, 120],
        "reason": "来款为法院执行专户，案号与裁定金额一致。",
        "tx_builder": _txs_court_award,
        "key_pool": [
            {"text": "资金来自法院执行专户，案号与民事裁定一致", "polarity": "counter"},
            {"text": "到账金额与裁定给付额勾稽，72 小时内无大额拆转", "polarity": "counter"},
            {"text": "企业提供裁定书扫描件，申请执行人户名匹配", "polarity": "counter"},
        ],
        "distractor_pool": [
            {"text": "夜间有一笔物业费代扣", "polarity": "context"},
            {"text": "备注曾写「往来」，后更正为执行款", "polarity": "support"},
        ],
        "summaries": [
            "施工企业账户于{day}收到法院执行专户 {amount} 万元。",
            "执行款入账 {amount} 万，案号可核，未即时拆转。",
            "{day} 裁定给付 {amount} 万到账，与文书金额一致。",
            "申请执行人户名匹配，到账 {amount} 万。",
            "执行专户转入 {amount} 万后余额留存。",
            "裁定批次到账 {amount} 万元，对手为法院专户。",
            "入账 {amount} 万且附裁定书，无短时拆分转出。",
            "执行来款 {amount} 万，时间{day}，与文书生效日吻合。",
        ],
    },
    {
        "tag": "demolition_comp",
        "gold": "exclude",
        "alert_type": "大额征收补偿入账",
        "industry": "房地产",
        "kind": "enterprise",
        "amounts": [85, 120, 156, 210],
        "reason": "土地储备中心拨付征收补偿，与征收决定金额一致。",
        "tx_builder": _txs_demolition,
        "key_pool": [
            {"text": "来款为土地储备中心，征收决定书金额与到账一致", "polarity": "counter"},
            {"text": "房屋评估报告与补偿明细可勾稽", "polarity": "counter"},
            {"text": "部分资金按约定划转结清在先按揭，路径可解释", "polarity": "counter"},
        ],
        "distractor_pool": [
            {"text": "次日有一笔维修基金代扣", "polarity": "context"},
            {"text": "中介服务费曾出现在对手列表，金额可解释", "polarity": "support"},
        ],
        "summaries": [
            "房企账户于{day}收到土地储备中心 {amount} 万元征收补偿。",
            "补偿款 {amount} 万入账，评估报告金额勾稽。",
            "{day} 征收决定对应款项 {amount} 万到账。",
            "储备中心拨付 {amount} 万，户名与被征收人一致。",
            "按揭尾款随后结清，主款 {amount} 万来源清楚。",
            "征收补偿 {amount} 万，决定书文号可核。",
            "入账 {amount} 万后按协议结清银行尾款。",
            "大额来款 {amount} 万，对手为土地储备中心。",
        ],
    },
    {
        "tag": "dual_pledge",
        "gold": "suggest_report",
        "alert_type": "频繁个人转入后转出",
        "industry": "建材批发",
        "kind": "enterprise",
        "amounts": [26, 35, 48, 62],
        "reason": "同一批货权向两家机构融资，多户放款后当日转出。",
        "tx_builder": _txs_dual_pledge,
        "key_pool": [
            {"text": "仓单编号在两家保理机构同时出现，货权重复融资", "polarity": "support"},
            {"text": "多个个人户短时放款后资金当日转往另一保理公司", "polarity": "support"},
            {"text": "仓储方书面否认该批货物可被二次质押", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "企业称正常周转，未能提供唯一货权证明", "polarity": "counter"},
            {"text": "开户满两年，KYC 为普通级", "polarity": "context"},
        ],
        "summaries": [
            "{day} 多名个人向企业转入后，资金当日转往保理公司，合计约 {amount} 万。",
            "短时多户放款聚合 {amount} 万，当日转出。",
            "个人户连入 {n} 笔后转往保理公司。",
            "放款合计 {amount} 万后数小时内转出，仓单重复使用。",
            "仓储方否认二次质押，金额约 {amount} 万。",
            "货权材料互相矛盾，资金路径 {amount} 万量级。",
            "{day} 放款—转出在数小时内完成。",
            "建材账户出现多户放款后转保理 {amount} 万。",
        ],
    },
    {
        "tag": "wager_proxy",
        "gold": "suggest_report",
        "alert_type": "频繁个人转入夜间转出",
        "industry": "个人-灵活就业",
        "kind": "individual",
        "amounts": [12, 18, 26, 35],
        "reason": "多户代付后夜间转出至单一私户，客户承认代收赌资。",
        "tx_builder": _txs_wager_proxy,
        "key_pool": [
            {"text": "客户承认账户被用于代收竞猜平台结算款", "polarity": "support"},
            {"text": "多名对手在夜间转出前数小时密集转入", "polarity": "support"},
            {"text": "无法说明与付款人的真实劳务或亲属关系", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "客户曾称代收房租，未能提供租约", "polarity": "counter"},
            {"text": "证件地址与常住地不一致", "polarity": "context"},
        ],
        "summaries": [
            "灵活就业账户于{day}收多笔代付后夜间转出 {amount} 万。",
            "个人户密集转入后收口到单一私户，金额约 {amount} 万。",
            "分散转入、夜间转出在同日完成。",
            "客户承认代收竞猜结算，金额 {amount} 万量级。",
            "付款人关系说不清，出账指向个人。",
            "短时资金收口路径清晰，合计 {amount} 万。",
            "入账标注代付，出账无对应发放名单。",
            "代付款项当日夜间清空至个人账户。",
        ],
    },
    {
        "tag": "fx_split",
        "gold": "suggest_report",
        "alert_type": "频繁跨境汇出",
        "industry": "跨境电商",
        "kind": "enterprise",
        "amounts": [],
        "reason": "连续多笔接近申报线的跨境汇出，缺乏真实贸易单证。",
        "tx_builder": _txs_fx_split,
        "key_pool": [
            {"text": "连续多笔汇出金额贴在申报线下方，对手均为境外户", "polarity": "support"},
            {"text": "报关与物流单据缺失，平台订单无法对应到汇出笔数", "polarity": "support"},
            {"text": "受益人名称高度相似，疑为同一控制人", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "企业称正常采购，只提供口头说明", "polarity": "counter"},
            {"text": "注册地与实际经营地不一致", "polarity": "context"},
        ],
        "summaries": [
            "跨境账户于{day}连续汇出 {n} 笔，合计约 {amount} 万，对手为境外户。",
            "短时多笔跨境支出聚合 {amount} 万，单笔贴申报线下方。",
            "境外户连收 {n} 笔，报关材料对不上。",
            "汇出合计 {amount} 万后账户余额接近清空。",
            "受益人名称相近，金额约 {amount} 万。",
            "平台订单无法对应到汇出笔数。",
            "{day} 跨境连汇在数小时内完成。",
            "电商账户出现贴线连汇 {amount} 万。",
        ],
    },
    {
        "tag": "staff_pass",
        "gold": "suggest_report",
        "alert_type": "大额对私转入后转出",
        "industry": "个人-灵活就业",
        "kind": "individual",
        "amounts": [18, 26, 35, 48],
        "reason": "员工户代收下游货款后夜间转给实际控制人。",
        "tx_builder": _txs_staff_pass,
        "key_pool": [
            {"text": "付款方均为某企业下游客户，员工本人无经营许可", "polarity": "support"},
            {"text": "入账后夜间全额转至该企业实际控制人账户", "polarity": "support"},
            {"text": "员工称「帮忙收款」，无法说明劳务对价", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "员工月度劳务费入账稳定", "polarity": "counter"},
            {"text": "近 30 日无其他大额支出", "polarity": "context"},
        ],
        "summaries": [
            "员工个人户于{day}收下游货款后夜间转出 {amount} 万。",
            "多户对公转入 {amount} 万，当日转给同一控制人。",
            "{day} 代收 {n} 笔货款后清空。",
            "无经营许可的个人户承接企业货款 {amount} 万。",
            "帮忙收款后夜间转出，金额约 {amount} 万。",
            "下游客户付款路径绕开企业基本户。",
            "个人户快进快出 {amount} 万，劳务对价说不清。",
            "代收货款当日转往控制人账户。",
        ],
    },
    {
        "tag": "shell_payroll",
        "gold": "suggest_report",
        "alert_type": "大额批量对私转出",
        "industry": "建筑工程",
        "kind": "enterprise",
        "amounts": [26, 35, 48, 62],
        "reason": "空壳企业以劳务费名义对私代发后资金回到出资方。",
        "tx_builder": _txs_shell_payroll,
        "key_pool": [
            {"text": "代发对手随即把款项转回原出资方，无真实用工", "polarity": "support"},
            {"text": "社保与个税申报人数远低于代发人数", "polarity": "support"},
            {"text": "企业无在施项目，经营场所为虚拟地址", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "企业称劳务分包，未能提供花名册", "polarity": "counter"},
            {"text": "开户满一年", "polarity": "context"},
        ],
        "summaries": [
            "施工企业于{day}向 {n} 名个人代发后，部分资金转回出资方，合计约 {amount} 万。",
            "劳务费名义对私 {amount} 万，收款人随即转回。",
            "代发 {n} 笔后款项转回出资方。",
            "无在施项目却批量代发 {amount} 万。",
            "社保人数与代发人数不匹配。",
            "虚拟地址企业出现对私代发 {amount} 万。",
            "{day} 往来款进入后当日对私拆出。",
            "空壳用工路径清晰，金额 {amount} 万量级。",
        ],
    },
    {
        "tag": "first_large",
        "gold": "observe",
        "alert_type": "大额转账待核",
        "industry": "个人-受雇",
        "kind": "individual",
        "amounts": [12, 18, 26, 35],
        "reason": "新开户首笔大额对公支付，对手可查但书面依据未齐。",
        "tx_builder": _txs_first_large,
        "key_pool": [
            {"text": "开户未满 30 日即出现首笔大额对公支付", "polarity": "context"},
            {"text": "对手工商存续，客户只提供口头「货款」说明", "polarity": "context"},
        ],
        "distractor_pool": [
            {"text": "月度劳务费入账稳定", "polarity": "counter"},
            {"text": "近窗未见夜间连笔拆转", "polarity": "counter"},
        ],
        "summaries": [
            "新开个人户于{day}转出 {amount} 万至对公户，书面依据未齐。",
            "大额支付 {amount} 万，对手存续可查，材料仍在补。",
            "{day} 单笔支出 {amount} 万，仅有口头货款说明。",
            "对公转出 {amount} 万后未再连转，缺书面依据。",
            "账户转出 {amount} 万，结算单承诺后补。",
            "大额支付 {amount} 万，受益人清楚但凭证缺口。",
            "转账 {amount} 万至贸易公司，材料收集中。",
            "单笔 {amount} 万外转，流水未见连笔快进快出。",
        ],
    },
    {
        "tag": "docs_pending",
        "gold": "observe",
        "alert_type": "遗产相关大额入账",
        "industry": "个人-继承",
        "kind": "individual",
        "amounts": [26, 35, 48, 62],
        "reason": "他行转入大额，继承材料不完整，尚无异常节奏。",
        "tx_builder": _txs_docs_pending,
        "key_pool": [
            {"text": "客户提交部分继承材料复印件，缺完整权利页", "polarity": "context"},
            {"text": "入账后口头用途在「治丧」与「购房」间变更", "polarity": "context"},
        ],
        "distractor_pool": [
            {"text": "账户历史以养老金为主，偶发亲友转入", "polarity": "counter"},
            {"text": "柜面口头称亲属关系，系统未登记", "polarity": "support"},
        ],
        "summaries": [
            "账户于{day}入账 {amount} 万，客户称遗产分配，材料缺页。",
            "大额转入 {amount} 万，继承材料不齐，口述前后不一。",
            "{day} 收到 {amount} 万，仅有部分复印件。",
            "遗产相关入账 {amount} 万，受益人关系待书面补证。",
            "个人账户突增 {amount} 万，材料不足以闭合继承链条。",
            "声称遗产到账 {amount} 万，缺完整权利证明。",
            "入账 {amount} 万后未能当场补齐文书全文。",
            "大额资金 {amount} 万到账，继承证明仍在收集。",
        ],
    },
]
