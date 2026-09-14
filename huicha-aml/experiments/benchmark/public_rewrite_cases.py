"""公开典型案例 → 脱敏 vignette 行（供 import_real_cases --public-rewrite）。

- 只改写公开报道/裁判摘要里的**银行侧可见形态**，不写入判决结果。
- 流水是按公开数量级重构的示意结构，不是原件账本。
- gold 全部 mapped 为 suggest_report：公开材料几乎都是已报送或已追诉，
  不能测排除/观察，禁止写入 RESULTS 主表，禁止写成准确率。
"""

from __future__ import annotations

import json

GOLD_PROVENANCE = "author-mapped-from-public-conclusion"
LEDGER_NOTE = "流水按公开报道的数量级与形态重构，不是原件账本。"
CAVEAT = (
    "公开改写探针（public-rewrite）。来源为监管通报、法院典型案例、义务机构宣传稿；"
    "gold 由作者按「公开结论为报送/追诉」映射，不是独立标注；"
    "12/12 均为 suggest_report，always_suggest_report 准确率为 1.0，"
    "命中不能证明能力，漏报（判成 observe/exclude）才有信息量；"
    "不能测排除/观察，禁止写入 RESULTS 主表，禁止写成准确率或生产能力。"
)

CITATIONS = [
    {
        "id": "SRC-01",
        "title": "“沉睡”账户突然“苏醒”银行警觉牵出洗钱大案（中行韶关 / 韶关中支，宣传转载）",
        "url": "https://www.zyfutures.com/fxqzsal/55439.jhtml",
        "used_by": ["PR-0001"],
    },
    {
        "id": "SRC-02",
        "title": "线上银行业务洗钱典型案例分析（中国电子银行网）",
        "url": "https://www.cebnet.com.cn/20200817/102683310.html",
        "used_by": ["PR-0002", "PR-0004"],
    },
    {
        "id": "SRC-03",
        "title": "商业银行对网络赌博类洗钱的风险防范（澎湃转载）",
        "url": "https://m.thepaper.cn/newsDetail_forward_29551063",
        "used_by": ["PR-0003"],
    },
    {
        "id": "SRC-04",
        "title": "人民法院依法惩治金融犯罪典型案例（最高人民法院）",
        "url": "https://www.court.gov.cn/zixun/xiangqing/372731.html",
        "used_by": ["PR-0005", "PR-0006"],
    },
    {
        "id": "SRC-05",
        "title": "反洗钱案例分享：员工出借账户转移集资款（义务机构宣传稿）",
        "url": "https://www.mingyafunds.com/mingya/contents/2026/3/26-ab2d863d37fd4569934ed4869ece8c03.html",
        "used_by": ["PR-0007"],
    },
    {
        "id": "SRC-06",
        "title": "转让公司却成为洗钱帮凶（郑州中院）",
        "url": "https://zzfy.hncourt.gov.cn/public/detail.php?id=29409",
        "used_by": ["PR-0008"],
    },
    {
        "id": "SRC-07",
        "title": "最高人民检察院、中国人民银行联合发布惩治洗钱犯罪典型案例",
        "url": "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/2025092212551439161/index.html",
        "used_by": ["PR-0009"],
    },
    {
        "id": "SRC-08",
        "title": "陈某等人掩饰、隐瞒犯罪所得案（案例库转写，银行侧形态）",
        "url": "http://www.drxsfd.com/xf/anli.asp?bh=5114",
        "used_by": ["PR-0010"],
    },
    {
        "id": "SRC-09",
        "title": "廖某掩饰、隐瞒犯罪所得案公开判决摘要（律师门户转写）",
        "url": "https://m.055110.com/xs/3/26723.html",
        "used_by": ["PR-0011"],
    },
    {
        "id": "SRC-10",
        "title": "银行柜员识破“跑分”洗钱陷阱（义务机构宣传稿）",
        "url": "https://www.dakuaiji.org.cn/article/xmzc_xwfg/detail346.html",
        "used_by": ["PR-0012"],
    },
]


def _tx(from_account: str, to_account: str, amount: float, occurred_at: str, channel: str, remark: str) -> dict:
    return {
        "from_account": from_account,
        "to_account": to_account,
        "amount": amount,
        "occurred_at": occurred_at,
        "channel": channel,
        "remark": remark,
    }


def _scatter_in(center: str, n: int, day: str, base: float = 680.0, channel: str = "网银") -> list[dict]:
    txs = []
    for i in range(n):
        hour = (i * 3) % 24
        minute = (i * 11) % 60
        amt = round(base + i * 37.5, 2)
        txs.append(
            _tx(
                f"in-{i:02d}-{800000 + i}",
                center,
                amt,
                f"{day} {hour:02d}:{minute:02d}:10",
                channel,
                "转账",
            )
        )
    return txs


def _row(
    *,
    case_id: str,
    tag: str,
    alert_type: str,
    industry: str,
    customer_kind: str,
    customer_name: str,
    amount: float,
    opened_at: str,
    summary: str,
    evidence: list[str],
    txs: list[dict],
    source_id: str,
    public_conclusion: str,
    annotation_reason: str,
) -> dict:
    cite = next(c for c in CITATIONS if c["id"] == source_id)
    return {
        "case_id": case_id,
        "gold": "suggest_report",
        "tag": tag,
        "alert_type": alert_type,
        "industry": industry,
        "customer_kind": customer_kind,
        "customer_name": customer_name,
        "amount": amount,
        "opened_at": opened_at,
        "summary": summary,
        "evidence": "|".join(evidence),
        "tx_json": json.dumps(txs, ensure_ascii=False),
        "annotation_reason": annotation_reason,
        "source_title": cite["title"],
        "source_url": cite["url"],
        "source_id": source_id,
        "public_conclusion": public_conclusion,
        "gold_provenance": GOLD_PROVENANCE,
        "ledger_note": LEDGER_NOTE,
    }


def public_rewrite_rows() -> list[dict]:
    c1 = "center-dormant"
    dormant_txs = [
        _tx("old-peer-a", c1, 28000, "2012-03-08 11:20:00", "柜面", "存入"),
        _tx("old-peer-b", c1, 15000, "2012-09-19 09:40:00", "转账", "往来"),
        _tx(c1, "fee", 3, "2014-06-01 00:00:01", "系统", "年费"),
        _tx(c1, "fee", 2, "2015-06-01 00:00:01", "系统", "短信费"),
        _tx("in-burst-01", c1, 860000, "2016-04-12 09:18:00", "转账", "转账"),
        _tx(c1, "atm-other-city", 858000, "2016-04-12 11:05:00", "ATM", "异地取现"),
        _tx("in-burst-02", c1, 920000, "2016-05-03 14:22:00", "转账", "转账"),
        _tx(c1, "atm-other-city", 918500, "2016-05-03 16:40:00", "柜面", "异地取现"),
        _tx("in-burst-03", c1, 1100000, "2016-07-21 10:11:00", "转账", "转账"),
        _tx(c1, "atm-other-city", 1097000, "2016-07-21 13:02:00", "ATM", "异地取现"),
        _tx("in-burst-04", c1, 760000, "2016-11-08 08:55:00", "转账", "转账"),
        _tx(c1, "atm-other-city", 758200, "2016-11-08 10:16:00", "柜面", "异地取现"),
    ]
    c2 = "center-scatter"
    scatter_txs = _scatter_in(c2, 14, "2020-06-18", base=4200) + [
        _tx(c2, "out-fixed", 61280, "2020-06-18 23:51:00", "手机银行", "转账"),
        *_scatter_in(c2, 12, "2020-06-19", base=3900),
        _tx(c2, "out-fixed", 54120, "2020-06-19 22:08:00", "手机银行", "转账"),
    ]
    c3 = "center-wager"
    wager_txs = _scatter_in(c3, 16, "2023-04-09", base=320, channel="网银") + [
        _tx(c3, "down-01", 7006, "2023-04-09 21:14:00", "手机银行", "UID-88**"),
        _tx(c3, "down-01", 7301, "2023-04-10 00:42:00", "手机银行", "转账"),
        _tx(c3, "down-02", 5504, "2023-04-10 03:18:00", "手机银行", "平台结算"),
        _tx(c3, "down-01", 5003, "2023-04-10 18:55:00", "手机银行", "转账"),
        _tx(c3, "down-03", 7501, "2023-04-11 02:07:00", "手机银行", "转账"),
    ]
    c4 = "center-pos"
    pos_txs = [
        _tx("pos-in-01", c4, 186000, "2020-08-03 10:02:00", "POS", "刷卡入账"),
        _tx(c4, "out-same-day", 185400, "2020-08-03 10:41:00", "网银", "转账"),
        _tx("pos-in-02", c4, 242000, "2020-08-04 09:18:00", "POS", "刷卡入账"),
        _tx(c4, "out-same-day", 241200, "2020-08-04 09:50:00", "网银", "转账"),
        _tx("pos-in-03", c4, 198500, "2020-08-05 11:22:00", "POS", "刷卡入账"),
        _tx(c4, "out-same-day", 197800, "2020-08-05 11:47:00", "手机银行", "转账"),
        _tx("pos-in-04", c4, 265000, "2020-08-06 16:05:00", "POS", "刷卡入账"),
        _tx(c4, "out-same-day", 264100, "2020-08-06 16:33:00", "网银", "转账"),
    ]
    c5 = "center-fx"
    fx_txs = [
        _tx("up-client-01", c5, 2800000, "2019-11-12 09:10:00", "转账", "货款"),
        _tx(c5, "designated-01", 2744000, "2019-11-12 09:40:00", "转账", "往来"),
        _tx("up-client-02", c5, 1950000, "2019-12-03 14:22:00", "转账", "货款"),
        _tx(c5, "designated-02", 1911000, "2019-12-03 14:51:00", "转账", "往来"),
        _tx("up-client-03", c5, 3200000, "2020-02-18 11:05:00", "转账", "货款"),
        _tx(c5, "designated-01", 3136000, "2020-02-18 11:28:00", "转账", "往来"),
        _tx("up-client-04", c5, 1500000, "2020-04-09 16:40:00", "转账", "货款"),
        _tx(c5, "designated-03", 1470000, "2020-04-09 17:02:00", "转账", "往来"),
    ]
    c6 = "center-cross"
    cross_txs = [
        _tx("soe-related", c6, 1200000, "2017-03-15 10:12:00", "转账", "借款"),
        _tx(c6, "ms-account-01", 1180000, "2017-03-15 15:40:00", "转账", "还款"),
        _tx("soe-related", c6, 980000, "2017-08-22 09:05:00", "转账", "借款"),
        _tx(c6, "ms-account-02", 970000, "2017-08-22 13:18:00", "转账", "往来"),
        _tx("soe-related", c6, 2100000, "2018-01-09 11:33:00", "转账", "借款"),
        _tx(c6, "ms-account-01", 2085000, "2018-01-09 16:02:00", "转账", "还款"),
        _tx("soe-related", c6, 1560000, "2018-06-27 08:44:00", "转账", "借款"),
        _tx(c6, "ms-account-03", 1542000, "2018-06-27 12:11:00", "转账", "往来"),
    ]
    c7 = "center-staff"
    staff_txs = [
        _tx("ctrl-01", c7, 860000, "2017-06-12 09:20:00", "转账", "往来"),
        _tx(c7, "cash-out", 850000, "2017-06-12 10:05:00", "柜面", "大额取现"),
        _tx("ctrl-02", c7, 420000, "2017-08-03 14:10:00", "转账", "往来"),
        _tx(c7, "ctrl-03", 418000, "2017-08-03 14:40:00", "转账", "转账"),
        _tx("ctrl-01", c7, 690000, "2017-10-19 11:00:00", "柜面", "取现存入"),
        _tx(c7, "ctrl-04", 688000, "2017-10-19 11:22:00", "柜面", "现金存入"),
        _tx("ctrl-02", c7, 510000, "2017-12-08 15:33:00", "转账", "往来"),
        _tx(c7, "cash-out", 505000, "2017-12-08 16:01:00", "柜面", "大额取现"),
    ]
    c8 = "center-shell"
    shell_txs = [
        _tx("new-co-01", c8, 8200000, "2023-06-18 09:05:00", "网银", "货款"),
        _tx(c8, "new-co-02", 8150000, "2023-06-18 09:40:00", "网银", "货款"),
        _tx("new-co-03", c8, 6400000, "2023-06-19 10:12:00", "网银", "往来"),
        _tx(c8, "new-co-04", 6380000, "2023-06-19 10:47:00", "网银", "往来"),
        _tx("new-co-05", c8, 9100000, "2023-06-20 14:22:00", "网银", "货款"),
        _tx(c8, "new-co-06", 9070000, "2023-06-20 14:58:00", "网银", "货款"),
        _tx("new-co-07", c8, 5300000, "2023-06-21 11:08:00", "网银", "往来"),
        _tx(c8, "new-co-08", 5280000, "2023-06-21 11:31:00", "网银", "往来"),
    ]
    c9 = "center-related"
    related_txs = [
        _tx("assoc-01", c9, 1800000, "2019-01-08 09:30:00", "转账", "往来"),
        _tx(c9, "cash-out", 1750000, "2019-01-08 11:05:00", "柜面", "大额取现"),
        _tx("assoc-02", c9, 960000, "2019-02-14 13:18:00", "转账", "往来"),
        _tx(c9, "assoc-03", 950000, "2019-02-14 15:40:00", "转账", "往来"),
        _tx("assoc-01", c9, 2200000, "2019-03-02 10:12:00", "转账", "往来"),
        _tx(c9, "cash-out", 2180000, "2019-03-02 16:22:00", "柜面", "大额取现"),
        _tx("assoc-04", c9, 1340000, "2019-03-21 09:44:00", "转账", "往来"),
        _tx(c9, "assoc-02", 1325000, "2019-03-21 10:18:00", "转账", "往来"),
    ]
    c10 = "center-night"
    night_txs = _scatter_in(c10, 10, "2021-01-15", base=18000, channel="手机银行") + [
        _tx(c10, "collect-01", 182400, "2021-01-15 23:12:00", "手机银行", "转账"),
        _tx("in-night-a", c10, 26400, "2021-01-16 01:08:00", "手机银行", "转账"),
        _tx("in-night-b", c10, 19800, "2021-01-16 02:41:00", "手机银行", "转账"),
        _tx(c10, "collect-01", 45800, "2021-01-16 03:05:00", "手机银行", "转账"),
        _tx("in-night-c", c10, 33100, "2021-01-16 22:50:00", "手机银行", "转账"),
        _tx(c10, "collect-02", 32900, "2021-01-16 23:18:00", "手机银行", "转账"),
    ]
    c11 = "center-lend"
    lend_txs = [
        _tx("up-01", c11, 18600, "2023-09-29 16:20:00", "网银", "转账"),
        _tx("up-02", c11, 22400, "2023-09-29 20:11:00", "手机银行", "转账"),
        _tx("up-03", c11, 15800, "2023-09-30 08:40:00", "网银", "转账"),
        _tx(c11, "cash-out", 35000, "2023-09-30 10:15:00", "柜面", "取现"),
        _tx("up-04", c11, 27100, "2023-09-30 14:22:00", "手机银行", "转账"),
        _tx(c11, "up-05", 26800, "2023-09-30 15:01:00", "手机银行", "转账"),
        _tx("up-06", c11, 19200, "2023-10-01 09:33:00", "网银", "转账"),
        _tx(c11, "cash-out", 19000, "2023-10-01 11:08:00", "柜面", "取现"),
    ]
    c12 = "center-run"
    run_txs = _scatter_in(c12, 11, "2024-05-06", base=800, channel="网银") + [
        _tx(c12, "try-cash", 18600, "2024-05-07 10:22:00", "柜面", "取现"),
        _tx("in-hlj", c12, 2600, "2024-05-07 13:40:00", "网银", "还款"),
        _tx("in-gd", c12, 4300, "2024-05-07 15:18:00", "网银", "还款"),
        _tx(c12, "try-cash-2", 22000, "2024-05-08 09:05:00", "柜面", "取现"),
    ]

    return [
        _row(
            case_id="PR-0001",
            tag="dormant_awakening",
            alert_type="休眠账户突发大额进出",
            industry="个人-灵活就业",
            customer_kind="individual",
            customer_name="钟某",
            amount=1100000,
            opened_at="2011-08-12",
            summary="长期无交易账户突然连续大额转入并在异地取现，余额接近零",
            evidence=[
                "2013年至2015年除系统扣费外无其他交易",
                "2016年起资金入账后数小时内在另一城市柜台或ATM取走",
                "客户职业与年交易规模明显不匹配，无法说明资金来源",
            ],
            txs=dormant_txs,
            source_id="SRC-01",
            public_conclusion="义务机构报送并移送，后牵出地下钱庄线索",
            annotation_reason="公开改写：休眠后突发快进快出异地取现",
        ),
        _row(
            case_id="PR-0002",
            tag="scatter_gather_24h",
            alert_type="分散转入集中转出",
            industry="个人-受雇",
            customer_kind="individual",
            customer_name="刘某",
            amount=61280,
            opened_at="2020-05-20",
            summary="新开个人卡每日多笔分散网银转入后经手机银行集中转出，含凌晨交易",
            evidence=[
                "转入对手来自多个地区不同银行自然人，单笔金额相近",
                "转出对手固定，当日进出基本轧平",
                "交易覆盖凌晨，客户称日常消费但无法指认对手",
            ],
            txs=scatter_txs,
            source_id="SRC-02",
            public_conclusion="义务机构研判为过渡性可疑并报送",
            annotation_reason="公开改写：分散进集中出且全天交易",
        ),
        _row(
            case_id="PR-0003",
            tag="wager_pass_through",
            alert_type="分散小额转入集中转出",
            industry="个人-网络销售",
            customer_kind="individual",
            customer_name="李某",
            amount=7501,
            opened_at="2021-11-03",
            summary="上游对手极为分散的小额入账后集中转出，部分附言像平台编号",
            evidence=[
                "上游对手数量远多于下游，单笔多为数百至数千",
                "下游集中且金额带零头，凌晨仍有转出",
                "客户称买卖虚拟物品，但附言与对手分布不像普通零售",
            ],
            txs=wager_txs,
            source_id="SRC-03",
            public_conclusion="义务机构限制非柜面并报送重点可疑",
            annotation_reason="公开改写：分散小额进、集中出、全天候",
        ),
        _row(
            case_id="PR-0004",
            tag="pos_pass_through",
            alert_type="POS入账后即转出",
            industry="个人-个体经营",
            customer_kind="individual",
            customer_name="吴某",
            amount=265000,
            opened_at="2019-02-11",
            summary="连续多日POS大额入账后同一小时内转出，账户几乎不留余额",
            evidence=[
                "单笔POS入账后约30至40分钟全额转出",
                "连续多日形态重复，无对应进货或工资发放痕迹",
                "客户身份与单日刷卡规模不匹配，无法提供真实经营凭证",
            ],
            txs=pos_txs,
            source_id="SRC-02",
            public_conclusion="义务机构研判为POS过渡性可疑并报送",
            annotation_reason="公开改写：POS快进快出不留余额",
        ),
        _row(
            case_id="PR-0005",
            tag="unlicensed_fx_layer",
            alert_type="大额快进快出对公转私人",
            industry="个人-汇兑中介",
            customer_kind="individual",
            customer_name="袁某",
            amount=3200000,
            opened_at="2016-04-01",
            summary="多笔大额转入后扣除尾差转给指定账户，客户称换汇但无牌照材料",
            evidence=[
                "入账后约半小时按固定比例扣减尾差转出",
                "对手多为新出现对公或个人账户，无持续贸易合同",
                "客户无法提供外汇业务资质或真实货物单据",
            ],
            txs=fx_txs,
            source_id="SRC-04",
            public_conclusion="公开典型案例：地下换汇通道协助资金出境",
            annotation_reason="公开改写：无牌换汇、快进快出、指定收款人",
        ),
        _row(
            case_id="PR-0006",
            tag="soe_to_ms_crossborder",
            alert_type="关联大额转入后外转",
            industry="个人-无固定职业",
            customer_kind="individual",
            customer_name="周某",
            amount=2100000,
            opened_at="2014-09-18",
            summary="园区国企关联账户多次大额转入后迅速转往资金中介类账户，客户称借款",
            evidence=[
                "对手与国有园区企业出纳或关联人账户重叠",
                "客户称私人借款但无法提供合同、利息约定或还款计划",
                "资金在当日或数小时内转出至疑似兑换/中介账户",
            ],
            txs=cross_txs,
            source_id="SRC-04",
            public_conclusion="公开典型案例：协助公款跨境转移",
            annotation_reason="公开改写：国企关联入账后转中介账户",
        ),
        _row(
            case_id="PR-0007",
            tag="employee_mule_cards",
            alert_type="员工账户大额取现拆转",
            industry="个人-公司职员",
            customer_kind="individual",
            customer_name="雷某",
            amount=860000,
            opened_at="2016-12-20",
            summary="职员卡接收实际控制人多个账户转入后大额取现、拆分转账或同柜先取后存",
            evidence=[
                "工资之外另有每月固定好处费入账，客户承认把卡交给上司使用",
                "存在柜面大额取现后立即存入其他关联账户",
                "对手为同一控制关系下的多个账户，客户说不清用途",
            ],
            txs=staff_txs,
            source_id="SRC-05",
            public_conclusion="公开案例：员工出借账户转移集资款；经办行因未尽报告义务被处罚",
            annotation_reason="公开改写：出借卡、拆分取现、同柜存取",
        ),
        _row(
            case_id="PR-0008",
            tag="idle_shell_company",
            alert_type="闲置对公户突发巨额进出",
            industry="医疗器械批发",
            customer_kind="enterprise",
            customer_name="某医疗器械有限公司",
            amount=9100000,
            opened_at="2019-03-08",
            summary="长期闲置对公户在一周内进出数千万，操作人与原法定代表人不符",
            evidence=[
                "开户后长期无经营流水，突然连续对公快进快出",
                "U盾与印鉴实际由非原管理人使用，客户称已口头转让公司",
                "对手多为新登记公司，无对应进销存或物流单据",
            ],
            txs=shell_txs,
            source_id="SRC-06",
            public_conclusion="公开案例：闲置公司对公户被用于转移诈骗资金",
            annotation_reason="公开改写：空壳对公户一周巨额快进快出",
        ),
        _row(
            case_id="PR-0009",
            tag="related_cash_layer",
            alert_type="关联账户频繁划转取现",
            industry="个人-无固定职业",
            customer_kind="individual",
            customer_name="曾某",
            amount=2200000,
            opened_at="2015-07-22",
            summary="与多名关联人账户之间大额频繁划转并夹杂柜面取现，来源去向均无法闭合",
            evidence=[
                "对手多为户籍或联系方式关联的个人账户",
                "大额取现与转账交替，账户余额不沉淀",
                "客户称生意周转但无经营实体、发票或场地租赁",
            ],
            txs=related_txs,
            source_id="SRC-07",
            public_conclusion="公开联合通报：关联账户大额取现与频繁划转",
            annotation_reason="公开改写：关联人账户取现分层",
        ),
        _row(
            case_id="PR-0010",
            tag="night_card_farm",
            alert_type="夜间多卡归集转账",
            industry="个人-灵活就业",
            customer_kind="individual",
            customer_name="陈某",
            amount=182400,
            opened_at="2020-08-01",
            summary="多名对手夜间向该卡转入后立即归集到少数账户，客户承认帮忙转账记账",
            evidence=[
                "交易集中在夜间，转入对手几乎不重复",
                "客户无法说明转账对象身份，称按上线指令操作",
                "同一时期名下多张卡出现同类夜间归集",
            ],
            txs=night_txs,
            source_id="SRC-08",
            public_conclusion="公开案例：组织多人银行卡夜间转移资金",
            annotation_reason="公开改写：夜间分散转入后归集",
        ),
        _row(
            case_id="PR-0011",
            tag="lent_cards_cashout",
            alert_type="出借账户后取现",
            industry="个人-灵活就业",
            customer_kind="individual",
            customer_name="廖某",
            amount=35000,
            opened_at="2022-04-16",
            summary="客户把多张卡及密码交给他人后按指示柜面取现，流水与本人收支明显不符",
            evidence=[
                "客户承认将三张卡交给不认识的人使用并获利",
                "取现资金来自刚入账的陌生对手，客户说不清还款或工资关系",
                "短期内多笔小额转入后集中取现",
            ],
            txs=lend_txs,
            source_id="SRC-09",
            public_conclusion="公开判决摘要：提供银行卡并按指示取现",
            annotation_reason="公开改写：出借多卡并代为取现",
        ),
        _row(
            case_id="PR-0012",
            tag="counter_hop_cashout",
            alert_type="全国分散转入后柜面取现",
            industry="个人-受雇",
            customer_kind="individual",
            customer_name="黄某",
            amount=22000,
            opened_at="2023-12-02",
            summary="账户对手遍布多省且互不重复，客户称朋友还款但金额前后矛盾并改去其他网点取现",
            evidence=[
                "转入对手地域跨度大、金额零碎、几乎不重复",
                "柜面问询时对金额和时间表述前后不一致",
                "在本网点暂缓后转往其他网点继续尝试取现",
            ],
            txs=run_txs,
            source_id="SRC-10",
            public_conclusion="义务机构暂缓取现并通报同城网点，模式符合跑分套现",
            annotation_reason="公开改写：分散入账后多网点尝试取现",
        ),
    ]
