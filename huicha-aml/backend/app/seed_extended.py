"""扩展合成精标集。gold_label 由模板写入，与规则同源，不是独立人工标注。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import Account, Alert, Customer, Transaction

PATTERNS = [
    ("exclude", "大额频繁", "批发备货样例"),
    ("suggest_report", "拆分存入后集中转出", "拆分样例"),
    ("suggest_report", "多账户资金归集", "归集样例"),
    ("observe", "大额转账（未登记亲属）", "观察样例"),
    ("exclude", "夜间聚集入账", "餐饮夜结样例"),
]


def seed_extended_cases(db: Session) -> None:
    _seed_case_f(db)
    _seed_pattern_range(db, 1, 80)
    db.commit()


def _seed_case_f(db: Session) -> None:
    if db.get(Alert, "ALT-F-20260910"):
        return
    if not db.get(Customer, "C-F"):
        db.add(
            Customer(
                id="C-F",
                name="王桂兰",
                kind="individual",
                industry="个人-退休",
                kyc_level="普通",
                opened_at="2010-05-20",
                city="西安",
                summary="养老金入账；本次转至未在白名单登记的对手，用途待核实。",
                watchlist=0,
            )
        )
    if not db.get(Account, "6222-F-6601"):
        db.add(Account(id="6222-F-6601", customer_id="C-F", opened_at="2010-05-20"))
    if not db.get(Transaction, "TX-F-01"):
        db.add(
            Transaction(
                id="TX-F-01",
                from_account="6222-F-6601",
                to_account="UNK-REL-09",
                amount=180000,
                occurred_at="2026-09-07 11:20:00",
                channel="柜面",
                remark="转账",
            )
        )
    db.add(
        Alert(
            id="ALT-F-20260910",
            customer_id="C-F",
            account_id="6222-F-6601",
            alert_type="大额转账（未登记亲属）",
            title="退休客户向未登记对手大额转账",
            amount=180000,
            created_at="2026-09-10 09:00:00",
            status="pending",
            demo_tag="F",
            upstream="规则引擎：个人大额 + 对手未登记",
            gold_label="observe",
        )
    )


def _seed_pattern_range(db: Session, start: int, end: int) -> None:
    for i in range(start, end + 1):
        gold, alert_type, title_prefix = PATTERNS[(i - 1) % len(PATTERNS)]
        cid = f"C-X{i:02d}"
        aid = f"6222-X{i:02d}"
        alt_id = f"ALT-EXT-{i:02d}"
        if db.get(Alert, alt_id):
            continue
        if gold == "exclude" and "夜间" in alert_type:
            industry, kind, name = "餐饮", "enterprise", f"演示餐饮{i:02d}"
            kyc = "普通"
        elif gold == "exclude":
            industry, kind, name = "日用百货批发", "enterprise", f"演示批发{i:02d}"
            kyc = "普通"
        elif gold == "observe":
            industry, kind, name = "个人-退休", "individual", f"演示退休{i:02d}"
            kyc = "普通"
        elif "拆分" in alert_type:
            industry, kind, name = "个人-无固定职业", "individual", f"演示拆分户{i:02d}"
            kyc = "普通"
        else:
            industry, kind, name = "贸易代理", "enterprise", f"演示贸易{i:02d}"
            kyc = "关注"

        if not db.get(Customer, cid):
            db.add(
                Customer(
                    id=cid,
                    name=name,
                    kind=kind,
                    industry=industry,
                    kyc_level=kyc,
                    opened_at="2024-01-15" if gold != "exclude" else "2017-06-01",
                    city="演示市",
                    summary=f"合成精标 {title_prefix}，期望结论 {gold}。",
                    watchlist=0,
                )
            )
        if not db.get(Account, aid):
            db.add(Account(id=aid, customer_id=cid, opened_at="2024-01-15"))

        txs: list[Transaction] = []
        if "拆分" in alert_type:
            for j in range(1, 10):
                txs.append(
                    Transaction(
                        id=f"TX-X{i:02d}-IN-{j:02d}",
                        from_account=f"CASH-{i:02d}{j:02d}",
                        to_account=aid,
                        amount=49500,
                        occurred_at=f"2026-08-{(j % 28) + 1:02d} 09:{10 + j}:00",
                        channel="ATM/现金",
                        remark="存入",
                    )
                )
            txs.append(
                Transaction(
                    id=f"TX-X{i:02d}-OUT-01",
                    from_account=aid,
                    to_account=f"UNK-OUT-{i:02d}",
                    amount=440000,
                    occurred_at="2026-09-01 22:10:00",
                    channel="网银",
                    remark="转出",
                )
            )
        elif "归集" in alert_type:
            for j in range(1, 5):
                txs.append(
                    Transaction(
                        id=f"TX-X{i:02d}-IN-{j:02d}",
                        from_account=f"UNK-P-{i:02d}-{j}",
                        to_account=aid,
                        amount=90000 + j * 1000,
                        occurred_at=f"2026-09-0{j} 10:00:00",
                        channel="手机银行",
                        remark="货款",
                    )
                )
            txs.append(
                Transaction(
                    id=f"TX-X{i:02d}-OUT-01",
                    from_account=aid,
                    to_account="6222-WL" if db.get(Account, "6222-WL") else f"UNK-WL-{i:02d}",
                    amount=300000,
                    occurred_at="2026-09-08 18:00:00",
                    channel="网银",
                    remark="咨询费",
                )
            )
        elif "夜间" in alert_type:
            for j in range(1, 6):
                txs.append(
                    Transaction(
                        id=f"TX-X{i:02d}-{j:02d}",
                        from_account=f"POS-X{i:02d}",
                        to_account=aid,
                        amount=15000 + j * 500,
                        occurred_at=f"2026-09-0{j} 22:30:00",
                        channel="POS",
                        remark="营业收入",
                    )
                )
        elif gold == "observe":
            txs.append(
                Transaction(
                    id=f"TX-X{i:02d}-01",
                    from_account=aid,
                    to_account=f"UNK-REL-{i:02d}",
                    amount=150000 + i * 1000,
                    occurred_at="2026-09-05 11:00:00",
                    channel="柜面",
                    remark="转账",
                )
            )
        else:
            peer_in = "6222-ST1" if db.get(Account, "6222-ST1") else f"UNK-ST-{i:02d}"
            peer_out = "6222-SUP" if db.get(Account, "6222-SUP") else f"UNK-SUP-{i:02d}"
            for j in range(1, 5):
                amt = 160000 + j * 5000
                txs.append(
                    Transaction(
                        id=f"TX-X{i:02d}-IN-{j:02d}",
                        from_account=peer_in,
                        to_account=aid,
                        amount=amt,
                        occurred_at=f"2026-08-{10 + j:02d} 10:00:00",
                        channel="对公转账",
                        remark="货款-备货",
                    )
                )
                txs.append(
                    Transaction(
                        id=f"TX-X{i:02d}-OUT-{j:02d}",
                        from_account=aid,
                        to_account=peer_out,
                        amount=round(amt * 0.8, 2),
                        occurred_at=f"2026-08-{10 + j:02d} 15:00:00",
                        channel="对公转账",
                        remark="向上游采购",
                    )
                )

        for t in txs:
            if not db.get(Transaction, t.id):
                db.add(t)
        db.add(
            Alert(
                id=alt_id,
                customer_id=cid,
                account_id=aid,
                alert_type=alert_type,
                title=f"{title_prefix}-{i:02d}",
                amount=float(txs[-1].amount),
                created_at=f"2026-09-{(i % 28) + 1:02d} 08:30:00",
                status="pending",
                demo_tag="",
                upstream="合成精标集",
                gold_label=gold,
            )
        )
