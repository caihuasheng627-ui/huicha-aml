from sqlalchemy.orm import Session

from .models import Account, Alert, Customer, Transaction


def seed_if_empty(db: Session) -> None:
    if db.query(Alert).count() > 0:
        return

    customers = [
        Customer(
            id="C-A",
            name="华东百货批发有限公司",
            kind="enterprise",
            industry="日用百货批发",
            kyc_level="普通",
            opened_at="2018-03-12",
            city="杭州",
            summary="成立于2016年，主营日用百货分销，下游约80家便利店与县级商超，季节性备货特征明显。",
            watchlist=0,
        ),
        Customer(
            id="C-B",
            name="张启明",
            kind="individual",
            industry="个人-无固定职业",
            kyc_level="普通",
            opened_at="2024-11-02",
            city="南昌",
            summary="开户不足一年，职业登记为自由职业，近月交易对手高度分散后突然集中转出。",
            watchlist=0,
        ),
        Customer(
            id="C-C",
            name="金辉商贸（演示）",
            kind="enterprise",
            industry="贸易代理",
            kyc_level="关注",
            opened_at="2025-06-18",
            city="深圳",
            summary="新设贸易公司，注册资本低，短期内多个个人账户向其归集资金。",
            watchlist=0,
        ),
        Customer(
            id="C-D",
            name="李秀英",
            kind="individual",
            industry="个人-退休",
            kyc_level="普通",
            opened_at="2012-01-08",
            city="成都",
            summary="养老金入账为主，偶发大额为子女购房转账（白名单亲属）。",
            watchlist=0,
        ),
        Customer(
            id="C-E",
            name="滨江餐饮管理有限公司",
            kind="enterprise",
            industry="餐饮",
            kyc_level="普通",
            opened_at="2019-09-01",
            city="南京",
            summary="连锁快餐结算户，周末现金流高峰。",
            watchlist=0,
        ),
        Customer(
            id="P-01",
            name="王磊",
            kind="individual",
            industry="个人",
            kyc_level="普通",
            opened_at="2025-07-01",
            city="深圳",
            summary="演示关联个人账户。",
            watchlist=0,
        ),
        Customer(
            id="P-02",
            name="陈婷",
            kind="individual",
            industry="个人",
            kyc_level="普通",
            opened_at="2025-07-03",
            city="深圳",
            summary="演示关联个人账户。",
            watchlist=0,
        ),
        Customer(
            id="P-03",
            name="赵强",
            kind="individual",
            industry="个人",
            kyc_level="普通",
            opened_at="2025-07-04",
            city="东莞",
            summary="演示关联个人账户。",
            watchlist=0,
        ),
        Customer(
            id="P-04",
            name="刘洋",
            kind="individual",
            industry="个人",
            kyc_level="普通",
            opened_at="2025-07-05",
            city="惠州",
            summary="演示关联个人账户。",
            watchlist=0,
        ),
        Customer(
            id="P-05",
            name="周敏",
            kind="individual",
            industry="个人",
            kyc_level="普通",
            opened_at="2025-07-06",
            city="深圳",
            summary="演示关联个人账户。",
            watchlist=0,
        ),
        Customer(
            id="SUP-1",
            name="浙北日化供应中心",
            kind="enterprise",
            industry="日用百货批发",
            kyc_level="普通",
            opened_at="2015-04-01",
            city="湖州",
            summary="华东百货上游供应商。",
            watchlist=0,
        ),
        Customer(
            id="STORE-1",
            name="余杭便利连锁",
            kind="enterprise",
            industry="零售",
            kyc_level="普通",
            opened_at="2017-08-01",
            city="杭州",
            summary="华东百货下游客户。",
            watchlist=0,
        ),
        Customer(
            id="SHELL-B",
            name="未核名对手方（演示）",
            kind="individual",
            industry="未知",
            kyc_level="缺失",
            opened_at="2026-01-01",
            city="未知",
            summary="拆分案例的集中转出对手，开户信息不完整。",
            watchlist=0,
        ),
        Customer(
            id="WL-1",
            name="演示关注名单-空壳咨询",
            kind="enterprise",
            industry="商务服务",
            kyc_level="高风险",
            opened_at="2023-01-01",
            city="未知",
            summary="合成关注名单主体，仅用于对照。",
            watchlist=1,
        ),
    ]
    db.add_all(customers)

    accounts = [
        Account(id="6222-A-8801", customer_id="C-A", opened_at="2018-03-12"),
        Account(id="6222-B-1908", customer_id="C-B", opened_at="2024-11-02"),
        Account(id="6222-C-3300", customer_id="C-C", opened_at="2025-06-18"),
        Account(id="6222-D-4412", customer_id="C-D", opened_at="2012-01-08"),
        Account(id="6222-E-5510", customer_id="C-E", opened_at="2019-09-01"),
        Account(id="6222-P01", customer_id="P-01", opened_at="2025-07-01"),
        Account(id="6222-P02", customer_id="P-02", opened_at="2025-07-03"),
        Account(id="6222-P03", customer_id="P-03", opened_at="2025-07-04"),
        Account(id="6222-P04", customer_id="P-04", opened_at="2025-07-05"),
        Account(id="6222-P05", customer_id="P-05", opened_at="2025-07-06"),
        Account(id="6222-SUP", customer_id="SUP-1", opened_at="2015-04-01"),
        Account(id="6222-ST1", customer_id="STORE-1", opened_at="2017-08-01"),
        Account(id="6222-WL", customer_id="WL-1", opened_at="2023-01-01"),
        Account(id="6222-OUT-B", customer_id="SHELL-B", opened_at="2026-01-01"),
    ]
    db.add_all(accounts)

    txs: list[Transaction] = []

    # Case A: wholesale, large but regular with known counterparties
    wholesale_days = [
        ("2026-08-03", 186000, "货款-备货"),
        ("2026-08-05", 142000, "货款"),
        ("2026-08-08", 210000, "中秋备货"),
        ("2026-08-12", 98000, "货款"),
        ("2026-08-15", 176000, "货款"),
        ("2026-08-19", 205000, "货款"),
        ("2026-08-22", 158000, "货款"),
        ("2026-08-26", 192000, "货款"),
        ("2026-08-29", 168000, "货款"),
        ("2026-09-02", 221000, "开学季备货"),
        ("2026-09-05", 149000, "货款"),
        ("2026-09-08", 188000, "货款"),
    ]
    for i, (day, amt, remark) in enumerate(wholesale_days, start=1):
        txs.append(
            Transaction(
                id=f"TX-A-IN-{i:02d}",
                from_account="6222-ST1",
                to_account="6222-A-8801",
                amount=amt,
                occurred_at=f"{day} 10:1{i % 6}:00",
                channel="对公转账",
                remark=remark,
            )
        )
        txs.append(
            Transaction(
                id=f"TX-A-OUT-{i:02d}",
                from_account="6222-A-8801",
                to_account="6222-SUP",
                amount=round(amt * 0.82, 2),
                occurred_at=f"{day} 15:2{i % 5}:00",
                channel="对公转账",
                remark="向上游采购",
            )
        )

    # Case B: structuring just below 50,000 then concentrated outflow
    for i in range(1, 20):
        day = 1 + (i % 12)
        txs.append(
            Transaction(
                id=f"TX-B-IN-{i:02d}",
                from_account=f"CASH-{i:02d}",
                to_account="6222-B-1908",
                amount=49800 if i % 3 else 49000,
                occurred_at=f"2026-09-{day:02d} 09:{10 + i}:00",
                channel="ATM/现金",
                remark="存入",
            )
        )
    txs.append(
        Transaction(
            id="TX-B-OUT-01",
            from_account="6222-B-1908",
            to_account="6222-OUT-B",
            amount=931200,
            occurred_at="2026-09-08 21:46:00",
            channel="网银",
            remark="转出",
        )
    )

    # Case C: five individuals funnel into 金辉
    funnel = [
        ("TX-C-01", "6222-P01", 128000, "2026-09-04 11:02:00"),
        ("TX-C-02", "6222-P02", 96000, "2026-09-04 11:18:00"),
        ("TX-C-03", "6222-P03", 152000, "2026-09-05 09:41:00"),
        ("TX-C-04", "6222-P04", 88000, "2026-09-05 14:05:00"),
        ("TX-C-05", "6222-P05", 141000, "2026-09-06 10:22:00"),
        ("TX-C-06", "6222-P01", 73000, "2026-09-07 16:11:00"),
        ("TX-C-07", "6222-P03", 119000, "2026-09-08 08:55:00"),
    ]
    for tid, src, amt, ts in funnel:
        txs.append(
            Transaction(
                id=tid,
                from_account=src,
                to_account="6222-C-3300",
                amount=amt,
                occurred_at=ts,
                channel="手机银行",
                remark="货款",
            )
        )
    txs.append(
        Transaction(
            id="TX-C-OUT-01",
            from_account="6222-C-3300",
            to_account="6222-WL",
            amount=420000,
            occurred_at="2026-09-08 19:03:00",
            channel="网银",
            remark="咨询费",
        )
    )

    # filler
    txs.append(
        Transaction(
            id="TX-D-01",
            from_account="6222-D-4412",
            to_account="RELATIVE-01",
            amount=300000,
            occurred_at="2026-08-20 10:00:00",
            channel="柜面",
            remark="子女购房",
        )
    )
    for i in range(1, 8):
        txs.append(
            Transaction(
                id=f"TX-E-{i:02d}",
                from_account="POS-E",
                to_account="6222-E-5510",
                amount=18000 + i * 800,
                occurred_at=f"2026-09-0{i} 22:10:00",
                channel="POS",
                remark="营业收入",
            )
        )

    db.add_all(txs)

    alerts = [
        Alert(
            id="ALT-A-20260910",
            customer_id="C-A",
            account_id="6222-A-8801",
            alert_type="大额频繁",
            title="对公账户短期内大额频繁往来",
            amount=188000,
            created_at="2026-09-10 08:12:00",
            status="pending",
            demo_tag="A",
            upstream="规则引擎：单日对公进出超过阈值",
        ),
        Alert(
            id="ALT-B-20260910",
            customer_id="C-B",
            account_id="6222-B-1908",
            alert_type="拆分存入后集中转出",
            title="多笔接近阈值存入后夜间集中转出",
            amount=931200,
            created_at="2026-09-10 08:14:00",
            status="pending",
            demo_tag="B",
            upstream="规则引擎：拆分特征 + 快进快出",
        ),
        Alert(
            id="ALT-C-20260910",
            customer_id="C-C",
            account_id="6222-C-3300",
            alert_type="多账户资金归集",
            title="多个个人账户向新设企业归集后外转",
            amount=797000,
            created_at="2026-09-10 08:16:00",
            status="pending",
            demo_tag="C",
            upstream="图规则模拟：多对一归集",
        ),
        Alert(
            id="ALT-D-20260909",
            customer_id="C-D",
            account_id="6222-D-4412",
            alert_type="大额转账",
            title="退休客户柜面大额转账",
            amount=300000,
            created_at="2026-09-09 16:40:00",
            status="pending",
            demo_tag="",
            upstream="规则引擎：个人大额",
        ),
        Alert(
            id="ALT-E-20260908",
            customer_id="C-E",
            account_id="6222-E-5510",
            alert_type="夜间聚集入账",
            title="餐饮结算户夜间多笔入账",
            amount=23600,
            created_at="2026-09-08 23:10:00",
            status="pending",
            demo_tag="",
            upstream="规则引擎：夜间交易笔数",
        ),
    ]
    db.add_all(alerts)
    db.commit()
