"""生成与规则模板不同源的独立合成标注集（v3：真实结构流水 + 规则分析层 + 极性标注）。

与 v2 的差别（对应实验有效性复审）：
- 每个 case 先生成真实结构的流水（ATM 案 → 多笔取现 + 回流；对倒案 → A→B→C→A 等），
  再调用产品的 `analyst_rules.analyze()` 得到规则层 findings（含 code / polarity），
  Judge 看到的输入与产品路径同构。
- 叙事项（调查记录）带 polarity（support / counter / context）：排除族必有反极性（counter）
  的开脱证据，上报族必有 support 证据，干扰项极性与主线相反或中性。
- 不再向 Judge 传 missing_evidence 输入（产品 `enrich_judge` 也不传），消除 observe 标签泄漏。
- 去掉所有「合成 / 占位」字样：客户名、客户摘要、同业基线说明、交易备注均为中性业务文本；
  kb_hits 由 `knowledge.retrieve_for_alert(alert_type, industry)` 检索。
- 证据编号：交易 `TX-`、叙事项 `IX-`（产品 `enrich_judge` 会过滤 `EV-` 前缀，改前缀后无需改产品代码）。

硬约束（由 tests/test_independent_benchmark_set.py 断言）：
- 去重后唯一输入 ≥ 200（指纹不含 case_id）
- 输入不出现家族名、gold、关键/干扰前缀、合成/占位字样、S/N 证据后缀
- annotation_reason / gold / role 仅存元数据，不进模型输入
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.analyst_rules import analyze  # noqa: E402
from app.knowledge import retrieve_for_alert  # noqa: E402
from app.tools import PEER_BASELINE  # noqa: E402

SEED = 20260912

# PEER_BASELINE 未覆盖的行业：中性同业说明，避免出现「缺少同业样本 / 演示」等元话语。
EXTRA_PEER = {
    "制造业": {"typical_monthly_in": 1_800_000, "typical_ticket": 150_000, "note": "制造企业月度货款回笼与薪酬代发并存，发薪日对私批量支出常见"},
    "农业合作社": {"typical_monthly_in": 300_000, "typical_ticket": 60_000, "note": "合作社收入以农产品销售与财政补贴为主，补贴到账呈批次性"},
    "投资咨询": {"typical_monthly_in": 500_000, "typical_ticket": 100_000, "note": "咨询服务费收付为主，同日多层大额过桥不属常规经营"},
    "互联网服务": {"typical_monthly_in": 900_000, "typical_ticket": 30_000, "note": "平台类账户入账分散属常态，需关注归集后向个人集中外转"},
    "个人-受雇": {"typical_monthly_in": 15_000, "typical_ticket": 12_000, "note": "受雇个人以固定工资入账为主，单笔大额需结合用途凭证"},
    "个人-购房": {"typical_monthly_in": 20_000, "typical_ticket": 15_000, "note": "购房期间可出现监管账户放款等一次性大额入账"},
    "个人-继承": {"typical_monthly_in": 8_000, "typical_ticket": 5_000, "note": "养老金为主的账户偶发亲属或遗产大额入账需结合权利证明"},
    "建材批发": {"typical_monthly_in": 1_200_000, "typical_ticket": 80_000, "note": "建材批发旺季备货支出抬升属常见经营节奏"},
    "建筑工程": {"typical_monthly_in": 2_000_000, "typical_ticket": 200_000, "note": "施工企业按节点收工程款、向分包方支付进度款"},
    "跨境电商": {"typical_monthly_in": 600_000, "typical_ticket": 25_000, "note": "跨境零售入账分散、出账对接物流与平台结算"},
    "房地产": {"typical_monthly_in": 800_000, "typical_ticket": 150_000, "note": "房企账户可见售房回款与拆迁、土地相关一次性大额"},
    "个人-灵活就业": {"typical_monthly_in": 20_000, "typical_ticket": 8_000, "note": "灵活就业账户以劳务与代收代付为主，大额需核背景"},
    "教育培训": {"typical_monthly_in": 80_000, "typical_ticket": 12_000, "note": "培训与院校账户可见学费收付与退学退费，退费应与学籍变动勾稽"},
    "个人-教师": {"typical_monthly_in": 18_000, "typical_ticket": 12_000, "note": "教师账户以薪酬为主，偶发持股分红或亲友往来需核书面依据"},
    "个人-医护": {"typical_monthly_in": 22_000, "typical_ticket": 10_000, "note": "医护账户以薪酬与单位互助报销为主，大额支出需核用途凭证"},
    "物流仓储": {"typical_monthly_in": 900_000, "typical_ticket": 80_000, "note": "仓储物流以运费与仓租收付为主，对手应能对应运单或仓单"},
    "种植合作社": {"typical_monthly_in": 280_000, "typical_ticket": 50_000, "note": "种植合作社收入以农产品销售与地租为主，租金应按决议批次到账"},
}

CUSTOMER_SUMMARY = {
    "制造业": "制造业企业客户，账户主要用于货款收付与员工薪酬代发。",
    "农业合作社": "农业合作社客户，账户用于农资采购与项目款项收付。",
    "投资咨询": "投资咨询类企业客户，账户以咨询服务费收付为主。",
    "互联网服务": "互联网服务企业客户，账户以平台款项收付为主。",
    "贸易代理": "贸易代理企业客户，账户以购销货款收付为主。",
    "个人-受雇": "受雇个人客户，账户以工资入账与日常消费为主。",
    "个人-购房": "个人客户，近期存在购房相关资金往来。",
    "个人-继承": "个人客户，账户以养老金入账为主。",
    "个人-无固定职业": "个人客户，无固定职业，账户流水以零散往来为主。",
    "建材批发": "建材批发企业客户，账户主要用于进货与下游配送结算。",
    "建筑工程": "建筑工程企业客户，账户用于工程款收付与分包结算。",
    "跨境电商": "跨境电商企业客户，账户用于平台货款与物流费用收付。",
    "房地产": "房地产企业客户，账户用于售房回款与项目支出。",
    "个人-灵活就业": "个人客户，灵活就业，账户以劳务收入与代收代付为主。",
    "教育培训": "教育培训相关个人或机构客户，账户可见学费与退费往来。",
    "个人-教师": "教师个人客户，账户以薪酬入账为主。",
    "个人-医护": "医护个人客户，账户以薪酬与互助报销为主。",
    "物流仓储": "物流仓储企业客户，账户用于运费与仓储费收付。",
    "种植合作社": "种植合作社客户，账户用于农产品销售与地租收付。",
}

ENTERPRISE_PREFIX = ["华辰", "鼎泰", "瑞和", "恒远", "盛邦", "中孚", "宏图", "远洲", "启明", "锦程", "凯达", "润泽"]
ENTERPRISE_SUFFIX = {
    "制造业": ["机械制造有限公司", "精密零部件有限公司", "电子科技有限公司"],
    "农业合作社": ["种植专业合作社", "养殖专业合作社", "农机服务合作社"],
    "投资咨询": ["投资咨询有限公司", "企业管理咨询有限公司"],
    "互联网服务": ["网络科技有限公司", "信息技术有限公司"],
    "贸易代理": ["贸易有限公司", "进出口代理有限公司", "商贸有限公司"],
    "建材批发": ["建材有限公司", "建材经销有限公司"],
    "建筑工程": ["建筑工程有限公司", "建设集团有限公司"],
    "跨境电商": ["跨境零售有限公司", "电子商务有限公司"],
    "房地产": ["房地产开发有限公司", "置业有限公司"],
    "物流仓储": ["物流有限公司", "仓储有限公司"],
    "种植合作社": ["种植专业合作社", "养殖专业合作社"],
    "教育培训": ["教育咨询有限公司", "培训有限公司"],
}
SURNAMES = ["王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙", "马", "朱", "胡", "郭", "林", "何"]

# 叙事族：gold / role 只在元数据；summary 模板不得含标签词。
# items: text / polarity(support|counter|context) / role(key|distractor)
FAMILIES: list[dict] = [
    {
        "tag": "payroll_batch",
        "gold": "exclude",
        "alert_type": "大额批量对私转出",
        "industry": "制造业",
        "kind": "enterprise",
        "amounts": [18, 26, 35, 48, 62, 85],
        "reason": "对私批次与在册工资表合计一致，属常规发薪。",
        "key_pool": [
            {"text": "对私转出合计与本月工资表人数×应发额一致", "polarity": "counter"},
            {"text": "发薪通道账户已在企业代发白名单登记", "polarity": "counter"},
            {"text": "转出时间落在固定发薪窗口，对手方均为在职员工账号", "polarity": "counter"},
        ],
        "distractor_pool": [
            {"text": "当日另有一笔 ATM 小额取现，与发薪批次无关", "polarity": "context", "flag": "atm_small"},
            {"text": "备注栏出现一次「借款」字样，经核对为员工备用金误填", "polarity": "support", "flag": "loan_remark"},
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
        "kind": "individual",
        "amounts": [12, 18, 26, 35, 48, 62],
        "reason": "入账与持牌险企赔付书编号一致。",
        "key_pool": [
            {"text": "对手方为持牌保险公司对公账户，入账备注含保单号", "polarity": "counter"},
            {"text": "赔付通知书金额与到账金额一致", "polarity": "counter"},
            {"text": "保单状态为已结案赔付，受益人与账户户名一致", "polarity": "counter"},
        ],
        "distractor_pool": [
            {"text": "客户当日另有一笔小额网购支出", "polarity": "context", "flag": "shopping"},
            {"text": "短信通知含「兑换」字样，实为积分商城文案", "polarity": "support"},
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
        "alert_type": "大额财政补贴入账",
        "industry": "农业合作社",
        "kind": "enterprise",
        "amounts": [26, 35, 48, 62, 85, 120],
        "reason": "财政专户入账且与公示批次金额一致，无二次拆转。",
        "key_pool": [
            {"text": "资金来自财政补贴专户，批次号与县区公示一致", "polarity": "counter"},
            {"text": "到账后 72 小时内无大额外转", "polarity": "counter"},
            {"text": "合作社提供补贴项目备案表，金额勾稽相符", "polarity": "counter"},
        ],
        "distractor_pool": [
            {"text": "夜间有一笔水电费自动扣款", "polarity": "context", "flag": "night_utility"},
            {"text": "会计备注曾写「过桥」，后更正为「备用金划转失败冲正」", "polarity": "support", "flag": "reversal"},
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
        "alert_type": "大额监管账户放款",
        "industry": "个人-购房",
        "kind": "individual",
        "amounts": [48, 62, 85, 120, 156, 210],
        "reason": "网签合同与监管账户放款指令一致。",
        "key_pool": [
            {"text": "放款指令来自住房资金监管账户", "polarity": "counter"},
            {"text": "网签合同买卖双方与账户户名一致", "polarity": "counter"},
            {"text": "放款金额与合同约定尾款一致", "polarity": "counter"},
        ],
        "distractor_pool": [
            {"text": "放款次日有一笔物业维修基金扣款", "polarity": "context", "flag": "maintenance_fee"},
            {"text": "中介账户曾出现在对手方列表，金额为服务费且可解释", "polarity": "support", "flag": "agent_fee"},
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
        "alert_type": "遗产过户大额入账",
        "industry": "个人-继承",
        "kind": "individual",
        "amounts": [26, 35, 48, 62, 85, 120],
        "reason": "继承材料不完整，用途说明前后不一致，需补证。",
        "key_pool": [
            {"text": "客户提交部分公证书复印件，缺继承权完整页", "polarity": "context"},
            {"text": "大额入账后用途说明在「治丧」与「购房」间变更", "polarity": "context"},
        ],
        "distractor_pool": [
            {"text": "账户历史以养老金为主，偶发亲友转入", "polarity": "counter", "flag": "friend_in"},
            {"text": "柜面曾口头称亲属关系，系统白名单未登记", "polarity": "support"},
        ],
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
        "kind": "individual",
        "amounts": [12, 18, 26, 35, 48],
        "reason": "单笔大额转出但合同/发票未齐，尚无清晰异常节奏，宜观察补证。",
        "key_pool": [
            {"text": "单笔对公转出金额较大，客户仅提供口头用途", "polarity": "context"},
            {"text": "交易对手工商存续，但合同原件尚未提交", "polarity": "context"},
        ],
        "distractor_pool": [
            {"text": "客户职业为受雇职员，月工资入账稳定", "polarity": "counter"},
            {"text": "近 30 日无夜间集中拆分特征", "polarity": "counter"},
        ],
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
        "alert_type": "频繁 ATM 取现回流",
        "industry": "个人-无固定职业",
        "kind": "individual",
        "amounts": [],  # 由取现笔数决定
        "reason": "多台 ATM 连续取现后回流，节奏异常。",
        "key_pool": [
            {"text": "同一证件短时在多台 ATM 取现", "polarity": "support"},
            {"text": "取现资金当日回流至新开个人账户", "polarity": "support"},
            {"text": "回流后迅速转出，无消费或工资解释", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "客户曾称「朋友周转」，未能提供书面说明", "polarity": "counter"},
            {"text": "开户时间短于 30 日", "polarity": "context", "flag": "new_account"},
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
        "alert_type": "关联对倒多层闭环",
        "industry": "贸易代理",
        "kind": "enterprise",
        "amounts": [35, 48, 62, 85, 120, 156],
        "reason": "关联公司互开票且无物流，资金闭环。",
        "key_pool": [
            {"text": "关联公司互开增值税发票，金额接近", "polarity": "support"},
            {"text": "资金在关联账户间当日闭环流转", "polarity": "support"},
            {"text": "物流轨迹缺失或与票面货物不符", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "合同模板高度雷同，仅对手名称替换", "polarity": "context"},
            {"text": "注册地址相同或相邻", "polarity": "context"},
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
        "alert_type": "现金存入后大额转出",
        "industry": "个人-无固定职业",
        "kind": "individual",
        "amounts": [],  # 由存现笔数决定
        "reason": "现金存入后迅速转至兑换商。",
        "key_pool": [
            {"text": "柜面/ATM 现金存入后短时全额转出", "polarity": "support"},
            {"text": "对手方标识为虚拟资产兑换商或场外承接户", "polarity": "support"},
            {"text": "客户无法说明资金合法来源", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "备注含「货款」但无合同", "polarity": "counter"},
            {"text": "开户证件地址与常住地不一致", "polarity": "context"},
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
        "alert_type": "层叠借款多层过桥",
        "industry": "投资咨询",
        "kind": "enterprise",
        "amounts": [48, 62, 85, 120, 156, 210],
        "reason": "无真实放款合同的层叠过桥。",
        "key_pool": [
            {"text": "借款合同关键要素缺失", "polarity": "support"},
            {"text": "资金当日经多层账户递减转出", "polarity": "support"},
            {"text": "对手方为新设空壳或无经营流水", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "备注统一填写「借款」", "polarity": "context"},
            {"text": "受益所有人信息披露不全", "polarity": "context"},
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
        "alert_type": "分散归集后短时外转",
        "industry": "互联网服务",
        "kind": "enterprise",
        "amounts": [12, 18, 26, 35, 48],
        "reason": "众筹归集后短时过桥至个人，具备典型分层特征。",
        "key_pool": [
            {"text": "平台入账后 2 小时内转出至个人账户", "polarity": "support"},
            {"text": "归集对手分散、外转对手集中", "polarity": "support"},
            {"text": "平台资质与项目材料无法核验", "polarity": "support"},
        ],
        "distractor_pool": [
            {"text": "对外宣传为互助项目，无备案编号", "polarity": "context"},
            {"text": "入账摘要含「捐赠」但无公益许可", "polarity": "context"},
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


# ---------------------------------------------------------------- 工具函数


def _opaque(rng: random.Random, prefix: str, case_id: str, salt: str) -> str:
    raw = f"{case_id}:{salt}:{rng.randrange(1 << 30)}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10].upper()
    return f"{prefix}-{digest}"


def _acc(rng: random.Random) -> str:
    return f"ACC-{rng.randint(100000, 999999)}"


def _ts(day: str, hour: int, minute: int, second: int = 0, offset_days: int = 0) -> str:
    base = datetime.strptime(day, "%Y-%m-%d") + timedelta(days=offset_days)
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return base.replace(hour=hour, minute=minute, second=second).strftime("%Y-%m-%d %H:%M:%S")


def _tx(src: str, dst: str, amount: float, when: str, channel: str, remark: str) -> dict:
    return {
        "from_account": src,
        "to_account": dst,
        "amount": round(float(amount), 2),
        "occurred_at": when,
        "channel": channel,
        "remark": remark,
    }


def _jitter(rng: random.Random, value: float, pct: float = 0.05) -> float:
    return value * (1 + rng.uniform(-pct, pct))


# ---------------------------------------------------------------- 各族流水构造
# 每个构造器返回 (txs, amount_wan, n)：amount_wan / n 用于格式化摘要。


def _txs_payroll_batch(rng, c, ctx):
    n = rng.choice([5, 8, 12, 17, 23])
    total = ctx["amount"] * 10000
    txs = []
    for k in range(2):
        txs.append(
            _tx(_acc(rng), c, _jitter(rng, total * 0.8), _ts(ctx["day"], rng.randint(9, 16), rng.randint(0, 59), 0, -rng.randint(3, 12)), "转账", "货款")
        )
        ctx["labels"][txs[-1]["from_account"]] = "下游客户"
    minute = rng.randint(20, 50)
    for k in range(n):
        emp = _acc(rng)
        ctx["labels"][emp] = "员工账户"
        remark = "工资"
        if "loan_remark" in ctx["flags"] and k == n // 2:
            remark = "借款"
        txs.append(_tx(c, emp, _jitter(rng, total / n, 0.08), _ts(ctx["day"], 9 + (minute + k) // 60, (minute + k) % 60, rng.randint(0, 59)), "代发", remark))
    if "atm_small" in ctx["flags"]:
        txs.append(_tx(c, "CASH-ATM-1", rng.choice([1000, 2000, 3000]), _ts(ctx["day"], 15, rng.randint(0, 59)), "ATM", "取现"))
        ctx["labels"]["CASH-ATM-1"] = "ATM 取现"
    return txs, ctx["amount"], n


def _txs_insurance_claim(rng, c, ctx):
    total = ctx["amount"] * 10000
    ins = _acc(rng)
    ctx["labels"][ins] = "保险公司对公账户"
    txs = []
    for k in range(2):
        emp = _acc(rng)
        ctx["labels"][emp] = "用人单位"
        txs.append(_tx(emp, c, rng.randint(8000, 15000), _ts(ctx["day"], 10, rng.randint(0, 59), 0, -(30 * (k + 1))), "代发", "工资"))
    txs.append(_tx(ins, c, total, _ts(ctx["day"], rng.randint(10, 15), rng.randint(0, 59)), "转账", f"理赔款 保单{rng.randint(10000000, 99999999)}"))
    if "shopping" in ctx["flags"]:
        txs.append(_tx(c, f"POS-{rng.randint(1000, 9999)}", rng.randint(300, 900), _ts(ctx["day"], 19, rng.randint(0, 59)), "网络支付", "网购消费"))
    return txs, ctx["amount"], 1


def _txs_gov_subsidy(rng, c, ctx):
    total = ctx["amount"] * 10000
    fin = _acc(rng)
    ctx["labels"][fin] = "财政零余额账户"
    txs = [_tx(fin, c, total, _ts(ctx["day"], rng.randint(9, 11), rng.randint(0, 59)), "转账", f"农业专项补贴 批次{rng.randint(2026001, 2026099)}")]
    for k in range(rng.randint(1, 2)):
        sup = _acc(rng)
        ctx["labels"][sup] = "农资供应商"
        txs.append(_tx(c, sup, _jitter(rng, total * 0.08), _ts(ctx["day"], rng.randint(9, 16), rng.randint(0, 59), 0, 4 + k), "转账", "农资采购"))
    if "night_utility" in ctx["flags"]:
        txs.append(_tx(c, "ACC-UTILITY-01", rng.choice([1260, 1830, 2410]), _ts(ctx["day"], 23, rng.randint(0, 59), 0, 1), "代扣", "电费代扣"))
        ctx["labels"]["ACC-UTILITY-01"] = "供电公司代扣"
    if "reversal" in ctx["flags"]:
        sub = _acc(rng)
        ctx["labels"][sub] = "本社备用金账户"
        txs.append(_tx(c, sub, 20000, _ts(ctx["day"], 14, 5, 0, 2), "转账", "备用金划转"))
        txs.append(_tx(sub, c, 20000, _ts(ctx["day"], 14, 9, 0, 2), "转账", "备用金划转冲正"))
    return txs, ctx["amount"], 1


def _txs_escrow_release(rng, c, ctx):
    total = ctx["amount"] * 10000
    esc = _acc(rng)
    ctx["labels"][esc] = "住房资金监管账户"
    txs = [_tx(esc, c, total, _ts(ctx["day"], rng.randint(10, 15), rng.randint(0, 59)), "转账", f"住房资金监管放款 网签{rng.randint(100000, 999999)}")]
    if "maintenance_fee" in ctx["flags"]:
        txs.append(_tx(c, "ACC-HOUSING-FUND", _jitter(rng, total * 0.02), _ts(ctx["day"], 10, rng.randint(0, 59), 0, 1), "代扣", "住宅专项维修资金"))
        ctx["labels"]["ACC-HOUSING-FUND"] = "维修资金专户"
    if "agent_fee" in ctx["flags"]:
        agent = _acc(rng)
        ctx["labels"][agent] = "房产中介"
        txs.append(_tx(c, agent, _jitter(rng, min(total * 0.015, 30000)), _ts(ctx["day"], 16, rng.randint(0, 59), 0, -rng.randint(2, 10)), "转账", "中介服务费"))
    return txs, ctx["amount"], 1


def _txs_inheritance_partial(rng, c, ctx):
    total = ctx["amount"] * 10000
    txs = []
    for k in range(3):
        txs.append(_tx("ACC-PENSION-01", c, rng.randint(3000, 5200), _ts(ctx["day"], 9, rng.randint(0, 59), 0, -(30 * (k + 1))), "代发", "养老金"))
    ctx["labels"]["ACC-PENSION-01"] = "社保发放账户"
    rel = _acc(rng)
    ctx["labels"][rel] = "个人账户"
    txs.append(_tx(rel, c, total, _ts(ctx["day"], rng.randint(10, 16), rng.randint(0, 59)), "转账", "遗产分配"))
    if "friend_in" in ctx["flags"]:
        fr = _acc(rng)
        ctx["labels"][fr] = "个人账户"
        txs.append(_tx(fr, c, rng.randint(500, 2000), _ts(ctx["day"], 18, rng.randint(0, 59), 0, -rng.randint(5, 20)), "转账", "转账"))
    return txs, ctx["amount"], 1


def _txs_purpose_docs_gap(rng, c, ctx):
    total = ctx["amount"] * 10000
    txs = []
    emp = _acc(rng)
    ctx["labels"][emp] = "用人单位"
    for k in range(3):
        txs.append(_tx(emp, c, rng.randint(9000, 16000), _ts(ctx["day"], 10, rng.randint(0, 59), 0, -(30 * (k + 1))), "代发", "工资"))
    corp = _acc(rng)
    ctx["labels"][corp] = "贸易公司"
    txs.append(_tx(c, corp, total, _ts(ctx["day"], rng.randint(10, 16), rng.randint(0, 59)), "转账", "货款"))
    return txs, ctx["amount"], 1


def _txs_atm_smurf(rng, c, ctx):
    n = rng.randint(4, 7)
    start_h = rng.choice([21, 22, 23])
    txs = []
    total = 0.0
    for k in range(n):
        amt = rng.choice([9000, 12000, 15000, 18000, 20000])
        total += amt
        dev = f"CASH-ATM-{k + 1}"
        ctx["labels"][dev] = f"ATM 设备{k + 1}"
        mins = start_h * 60 + rng.randint(0, 20) + k * rng.randint(8, 15)
        txs.append(_tx(c, dev, amt, _ts(ctx["day"], (mins // 60) % 24, mins % 60, rng.randint(0, 59), mins // 1440), "ATM", "取现"))
    new_acc = _acc(rng)
    ctx["labels"][new_acc] = "新开个人账户"
    for k in range(min(n, 3)):
        txs.append(_tx(f"CASH-ATM-{k + 1}", new_acc, total / min(n, 3), _ts(ctx["day"], rng.randint(8, 11), rng.randint(0, 59), 0, 1), "现金存入", "存款"))
    out = _acc(rng)
    ctx["labels"][out] = "个人账户"
    txs.append(_tx(new_acc, out, total, _ts(ctx["day"], rng.randint(12, 14), rng.randint(0, 59), 0, 1), "转账", "转账"))
    return txs, round(total / 10000, 1), n


def _txs_invoice_circular(rng, c, ctx):
    total = ctx["amount"] * 10000
    rel1, rel2 = _acc(rng), _acc(rng)
    ctx["labels"][rel1] = "关联贸易公司甲"
    ctx["labels"][rel2] = "关联贸易公司乙"
    loops = rng.choice([1, 2])
    txs = []
    hour = rng.randint(9, 11)
    for i in range(loops):
        base = total / loops
        inv = rng.randint(10000000, 99999999)
        txs.append(_tx(c, rel1, base, _ts(ctx["day"], hour, 5 + i, 0), "转账", f"货款 发票{inv}"))
        txs.append(_tx(rel1, rel2, base * 0.98, _ts(ctx["day"], hour + 1, 10 + i, 0), "转账", f"货款 发票{inv + 1}"))
        txs.append(_tx(rel2, c, base * 0.97, _ts(ctx["day"], hour + 3, 20 + i, 0), "转账", f"货款 发票{inv + 2}"))
        hour += 4
    return txs, ctx["amount"], loops * 3


def _txs_crypto_onramp(rng, c, ctx):
    n = rng.randint(8, 10)
    txs = []
    total = 0.0
    for k in range(n):
        amt = rng.choice([49000, 49200, 49500, 49800, 49900])
        total += amt
        ch = f"CASH-{k + 1}"
        ctx["labels"][ch] = "现金存入"
        txs.append(_tx(ch, c, amt, _ts(ctx["day"], rng.randint(9, 18), rng.randint(0, 59), 0, -(k // 5)), "现金存入", "存款"))
    otc = _acc(rng)
    ctx["labels"][otc] = "数字资产兑换商承接户"
    txs.append(_tx(c, otc, total, _ts(ctx["day"], rng.randint(19, 20), rng.randint(0, 59)), "转账", "货款"))
    return txs, round(total / 10000, 1), n


def _txs_nested_shell_loan(rng, c, ctx):
    total = ctx["amount"] * 10000
    lender, b, cc, d = _acc(rng), _acc(rng), _acc(rng), _acc(rng)
    ctx["labels"].update({lender: "出借方", b: "新设企业甲", cc: "新设企业乙", d: "个人账户"})
    hour = rng.randint(9, 10)
    txs = [
        _tx(lender, c, total, _ts(ctx["day"], hour, 5), "转账", "借款"),
        _tx(c, b, total * 0.95, _ts(ctx["day"], hour + 1, 15), "转账", "借款"),
        _tx(b, cc, total * 0.90, _ts(ctx["day"], hour + 2, 40), "转账", "借款"),
        _tx(cc, d, total * 0.85, _ts(ctx["day"], hour + 4, 10), "转账", "借款"),
    ]
    return txs, ctx["amount"], 3


def _txs_crowdfund_layering(rng, c, ctx):
    n = rng.randint(5, 9)
    total = ctx["amount"] * 10000
    txs = []
    hour = rng.randint(9, 12)
    for k in range(n):
        src = _acc(rng)
        ctx["labels"][src] = "个人账户"
        txs.append(_tx(src, c, _jitter(rng, total / n, 0.2), _ts(ctx["day"], hour, rng.randint(0, 59)), "转账", rng.choice(["项目支持", "捐赠", "众筹"])))
    dst = _acc(rng)
    ctx["labels"][dst] = "个人账户"
    txs.append(_tx(c, dst, total, _ts(ctx["day"], hour + 2, rng.randint(0, 30)), "转账", "转账"))
    return txs, ctx["amount"], n


TX_BUILDERS = {
    "payroll_batch": _txs_payroll_batch,
    "insurance_claim": _txs_insurance_claim,
    "gov_subsidy": _txs_gov_subsidy,
    "escrow_release": _txs_escrow_release,
    "inheritance_partial": _txs_inheritance_partial,
    "purpose_docs_gap": _txs_purpose_docs_gap,
    "atm_smurf": _txs_atm_smurf,
    "invoice_circular": _txs_invoice_circular,
    "crypto_onramp": _txs_crypto_onramp,
    "nested_shell_loan": _txs_nested_shell_loan,
    "crowdfund_layering": _txs_crowdfund_layering,
}


# ---------------------------------------------------------------- 产品同构的 bundle 构件


def _baseline(customer: dict, txs: list[dict], account_id: str) -> dict:
    inflow = [t for t in txs if t["to_account"] == account_id]
    outflow = [t for t in txs if t["from_account"] == account_id]
    in_sum = round(sum(t["amount"] for t in inflow), 2)
    out_sum = round(sum(t["amount"] for t in outflow), 2)
    peer = PEER_BASELINE.get(customer["industry"]) or EXTRA_PEER.get(customer["industry"]) or {
        "typical_monthly_in": 100_000,
        "typical_ticket": 20_000,
        "note": "该行业暂无同业样本区间，请结合客户经营规模判断",
    }
    return {
        "industry": customer["industry"],
        "sample_in_count": len(inflow),
        "sample_out_count": len(outflow),
        "sample_in_sum": in_sum,
        "sample_out_sum": out_sum,
        "avg_in_ticket": round(in_sum / max(len(inflow), 1), 2),
        "peer_typical_monthly_in": peer["typical_monthly_in"],
        "peer_typical_ticket": peer["typical_ticket"],
        "peer_note": peer["note"],
        "in_sum_vs_peer": round(in_sum / peer["typical_monthly_in"], 2) if peer["typical_monthly_in"] else None,
    }


def _graph(account_id: str, center_label: str, txs: list[dict], labels: dict[str, str]) -> dict:
    nodes = {account_id: {"id": account_id, "label": center_label, "kind": "center"}}
    edges: dict[tuple[str, str], dict] = {}
    for t in txs:
        for raw in (t["from_account"], t["to_account"]):
            if raw not in nodes:
                nodes[raw] = {"id": raw, "label": labels.get(raw, raw), "kind": "counterparty"}
        key = (t["from_account"], t["to_account"])
        if key not in edges:
            edges[key] = {"id": t["id"], "source": key[0], "target": key[1], "amount": 0.0, "count": 0, "tx_ids": []}
        edges[key]["amount"] = round(edges[key]["amount"] + t["amount"], 2)
        edges[key]["count"] += 1
        edges[key]["tx_ids"].append(t["id"])
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def _customer_name(rng: random.Random, fam: dict) -> str:
    if fam["kind"] == "enterprise":
        suffixes = ENTERPRISE_SUFFIX.get(fam["industry"]) or fam.get("name_suffixes") or ["有限公司"]
        return rng.choice(ENTERPRISE_PREFIX) + rng.choice(suffixes)
    return rng.choice(SURNAMES) + "**"


def _tx_builder(fam: dict):
    if callable(fam.get("tx_builder")):
        return fam["tx_builder"]
    return TX_BUILDERS[fam["tag"]]


def _fingerprint(case: dict) -> str:
    vig = case["vignette"]
    blob = json.dumps(
        {
            "alert_type": vig["alert_type"],
            "industry": vig["industry"],
            "summary": vig["summary"],
            "evidence": sorted(e["text"] for e in vig["candidate_evidence"]),
            "txs": sorted((t["amount"], t["occurred_at"], t["remark"]) for t in vig["transactions"]),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _slim_kb(hits: list[dict]) -> list[dict]:
    return [{"id": h.get("id"), "kind": h.get("kind"), "title": h.get("title"), "snippet": h.get("snippet")} for h in hits]


# ---------------------------------------------------------------- 主流程


def build_case(rng: random.Random, fam: dict, case_id: str, seq: int, *, note_polarity: bool = True) -> dict:
    """note_polarity=False：叙事项一律 context，极性只保留产品规则层真正触发的（消融 2）。"""
    day = f"2026-{rng.randint(3, 9):02d}-{rng.randint(1, 28):02d}"
    account_id = f"ACC-{rng.randint(100000, 999999)}"
    customer_id = f"C-{rng.randint(10000, 99999)}"

    key_items = rng.sample(fam["key_pool"], rng.randint(1, min(2, len(fam["key_pool"]))))
    n_dis = rng.randint(0, min(2, len(fam["distractor_pool"])))
    dis_items = rng.sample(fam["distractor_pool"], n_dis) if n_dis else []
    flags = {it["flag"] for it in dis_items if it.get("flag")}

    ctx = {
        "amount": rng.choice(fam["amounts"]) if fam["amounts"] else 0,
        "day": day,
        "flags": flags,
        "labels": {},
    }
    raw_txs, amount_wan, n_eff = _tx_builder(fam)(rng, account_id, ctx)
    raw_txs.sort(key=lambda t: t["occurred_at"])
    txs = []
    for k, t in enumerate(raw_txs):
        txs.append({"id": _opaque(rng, "TX", case_id, f"tx{k}"), **t})

    summary = rng.choice(fam["summaries"]).format(amount=amount_wan, n=n_eff, day=day)

    opened_at = f"{rng.randint(2018, 2025)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    if "new_account" in flags:
        opened_at = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=rng.randint(7, 25))).strftime("%Y-%m-%d")
    customer = {
        "id": customer_id,
        "name": _customer_name(rng, fam),
        "kind": fam["kind"],
        "industry": fam["industry"],
        "opened_at": opened_at,
        "kyc_level": rng.choice(["普通", "普通", "标准"]),
        "summary": fam.get("customer_summary") or CUSTOMER_SUMMARY[fam["industry"]],
    }
    in_amt = sum(t["amount"] for t in txs if t["to_account"] == account_id)
    out_amt = sum(t["amount"] for t in txs if t["from_account"] == account_id)
    alert = {
        "id": case_id,
        "alert_type": fam["alert_type"],
        "upstream": "monitoring-v3",
        "account_id": account_id,
        "customer_id": customer_id,
        "amount": round(max(in_amt, out_amt), 2),
        "created_at": _ts(day, 8, 30, 0, 1),
    }
    baseline = _baseline(customer, txs, account_id)
    graph = _graph(account_id, customer["name"], txs, ctx["labels"])
    watch_hits: list[dict] = []

    rule_findings = analyze(
        alert=alert,
        customer=customer,
        txs=txs,
        account_id=account_id,
        baseline=baseline,
        watch_hits=watch_hits,
        graph=graph,
    )["findings"]

    # 叙事项 → 调查记录 finding（带极性），顺序打乱，避免 key 恒在前。
    items = [{**it, "role": "key"} for it in key_items] + [{**it, "role": "distractor"} for it in dis_items]
    rng.shuffle(items)
    candidate_evidence: list[dict] = []
    note_findings: list[dict] = []
    gold_support: list[str] = []
    gold_contra: list[str] = []
    for j, it in enumerate(items):
        eid = _opaque(rng, "IX", case_id, f"note{j}")
        candidate_evidence.append({"id": eid, "text": it["text"]})
        note_findings.append(
            {
                "code": "case-note",
                "title": f"调查记录{j + 1}",
                "detail": it["text"],
                "evidence_ids": [eid],
                "polarity": it["polarity"] if note_polarity else "context",
            }
        )
        if it["role"] == "key":
            gold_support.append(eid)
        elif (fam["gold"] == "exclude" and it["polarity"] == "support") or (
            fam["gold"] == "suggest_report" and it["polarity"] == "counter"
        ):
            gold_contra.append(eid)

    brief = {
        "code": "alert-brief",
        "title": "线索摘要",
        "detail": summary,
        "evidence_ids": [t["id"] for t in txs[:3]],
        "polarity": "context",
    }
    findings = [brief, *rule_findings, *note_findings]

    kb_hits = _slim_kb(retrieve_for_alert(fam["alert_type"], fam["industry"], as_of=day))
    allowed = sorted(
        {t["id"] for t in txs}
        | {e["id"] for e in candidate_evidence}
        | {h["id"] for h in kb_hits if h.get("id")}
        | {customer_id, account_id}
    )

    return {
        "case_id": case_id,
        "gold": fam["gold"],
        "tag": fam["tag"],
        "annotation_reason": f"[{fam['tag']}] {fam['reason']}",
        "gold_support_ids": gold_support,
        "gold_contradict_ids": gold_contra,
        "gold_evidence_ids": list(gold_support),
        "rule_finding_codes": [f["code"] for f in rule_findings],
        "vignette": {
            "alert_type": fam["alert_type"],
            "industry": fam["industry"],
            "summary": summary,
            "alert": alert,
            "customer": customer,
            "findings": findings,
            "transactions": txs,
            "baseline": baseline,
            "graph": graph,
            "kb_hits": kb_hits,
            "watch_hits": watch_hits,
            "allowed_evidence": allowed,
            "candidate_evidence": candidate_evidence,
        },
    }


def build_cases(
    n: int = 240,
    *,
    families: list[dict] | None = None,
    seed: int = SEED,
    note_polarity: bool = True,
    id_prefix: str = "IND",
) -> list[dict]:
    families = families or FAMILIES
    rng = random.Random(seed)
    cases: list[dict] = []
    seen: set[str] = set()
    attempts = 0
    i = 0
    while len(cases) < n and attempts < n * 40:
        attempts += 1
        fam = families[i % len(families)]
        i += 1
        case_id = f"{id_prefix}-{len(cases) + 1:04d}"
        case = build_case(rng, fam, case_id, len(cases) + 1, note_polarity=note_polarity)
        fp = _fingerprint(case)
        if fp in seen:
            continue
        seen.add(fp)
        case["fingerprint"] = fp
        cases.append(case)
    if len(seen) < 200:
        raise RuntimeError(f"唯一输入不足：n_unique={len(seen)} < 200")
    return cases


BASE_CAVEAT = (
    "与 seed_extended 规则模板不同源的组合采样合成集；"
    "流水按叙事族真实结构生成并经产品 analyst_rules.analyze() 产出规则层 findings；"
    "不向 Judge 传 missing_evidence；"
    "输入已去除家族名/关键干扰前缀/合成占位字样；annotation_reason 仅元数据；"
    "不是人工专家标注；禁止写成生产准确率。"
)

VARIANTS = {
    # 主集：叙事项带极性
    "v3": {
        "file": "independent_set.json",
        "source": "narrative_vignette_v3_rules_layer",
        "data_note": "synthetic-independent-v3",
        "n": 240,
        "seed": SEED,
        "note_polarity": True,
        "id_prefix": "IND",
        "caveat_extra": "叙事项带 support/counter/context 极性。",
    },
    # 消融 2：同族同种子，叙事项极性全部置为 context，只保留规则层极性
    "nopolarity": {
        "file": "independent_set_nopolarity.json",
        "source": "narrative_vignette_v3_rules_layer_nopolarity",
        "data_note": "synthetic-independent-v3-nopolarity",
        "n": 240,
        "seed": SEED,
        "note_polarity": False,
        "id_prefix": "IND",
        "caveat_extra": "叙事项极性一律 context；极性只来自产品规则层真正触发的 finding。用于拆解「极性提示」对 Judge 的贡献。",
    },
    # 消融 1：prompt 盲区 hold-out——叙事不含 judge_v3 例举词，类型学在例举之外
    "blind": {
        "file": "blind_set.json",
        "source": "narrative_vignette_blind_holdout",
        "data_note": "synthetic-blind-holdout-v1",
        "n": 220,
        "seed": SEED + 7,
        "note_polarity": True,
        "id_prefix": "BLD",
        "caveat_extra": "叙事文本不含 judge_v3 判定标准中例举的任何类型学词；类型学形态在例举之外。规则层 finding 文本为产品输出，不受禁词约束。",
    },
    # 消融 3：结构盲区——禁词同盲区，且流水不触发 structuring/funnel/night-out/layering
    "blind_struct": {
        "file": "struct_set.json",
        "source": "narrative_vignette_blind_struct",
        "data_note": "synthetic-blind-struct-v1",
        "n": 220,
        "seed": SEED + 19,
        "note_polarity": True,
        "id_prefix": "BST",
        "caveat_extra": "叙事禁词与盲区集相同；流水刻意不触发 structuring/funnel/night-out/layering，规则层只留 alert-trigger。上报信号只在叙事项与对手关系。用于测 Judge 是否依赖规则层结构话术。",
    },
}


def _families_for(variant: str) -> list[dict]:
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    if variant == "blind":
        from blind_families import BLIND_FAMILIES  # noqa: E402

        return BLIND_FAMILIES
    if variant == "blind_struct":
        from struct_families import STRUCT_FAMILIES  # noqa: E402

        return STRUCT_FAMILIES
    return FAMILIES


def _assert_struct_rules(cases: list[dict]) -> None:
    from struct_families import STRUCT_FORBIDDEN_RULES  # noqa: E402

    for case in cases:
        codes = set(case.get("rule_finding_codes") or [])
        bad = codes & set(STRUCT_FORBIDDEN_RULES)
        if bad:
            raise RuntimeError(f"{case['case_id']} {case['tag']} 触发了结构规则 {sorted(bad)}")
        extra = codes - {"alert-trigger"}
        if extra:
            raise RuntimeError(f"{case['case_id']} {case['tag']} 规则层多出 {sorted(extra)}")
        if "alert-trigger" not in codes:
            raise RuntimeError(f"{case['case_id']} {case['tag']} 缺少 alert-trigger")


def build_payload(variant: str) -> dict:
    spec = VARIANTS[variant]
    families = _families_for(variant)
    cases = build_cases(
        spec["n"],
        families=families,
        seed=spec["seed"],
        note_polarity=spec["note_polarity"],
        id_prefix=spec["id_prefix"],
    )
    if variant == "blind_struct":
        _assert_struct_rules(cases)
    split = {
        "v3": "independent",
        "nopolarity": "independent",
        "blind": "blind_holdout",
        "blind_struct": "blind_struct_holdout",
    }.get(variant, "independent")
    return {
        "data_note": spec["data_note"],
        "split": split,
        "variant": variant,
        "source": spec["source"],
        "seed": spec["seed"],
        "n": len(cases),
        "n_unique": len({c["fingerprint"] for c in cases}),
        "families": [f["tag"] for f in families],
        "judge_input_contract": "enrich_judge(alert, customer, findings, transactions, baseline, kb_hits, allowed_evidence)；不传 missing_evidence",
        "caveat": BASE_CAVEAT + spec["caveat_extra"],
        "cases": cases,
    }


def main(argv: list[str] | None = None) -> Path:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="v3")
    args = parser.parse_args(argv)
    payload = build_payload(args.variant)
    out = Path(__file__).with_name(VARIANTS[args.variant]["file"])
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out} variant={args.variant} n={payload['n']} n_unique={payload['n_unique']}")
    return out


if __name__ == "__main__":
    main()
