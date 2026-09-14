"""One-off builder: emit knowledge_* statute modules from official gazette dumps."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DUMP = Path(r"C:\Users\蔡华升\.cursor\projects\c-Users-Desktop-icbc\agent-tools")
OUT = Path(__file__).resolve().parents[1] / "app"

CN_NUM = "零〇一二三四五六七八九十百千0-9"


def cn_to_int(s: str) -> int:
    s = s.replace("〇", "零")
    digits = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    total = 0
    if "百" in s:
        i = s.index("百")
        total += digits.get(s[:i] or "一", 1) * 100
        s = s[i + 1 :]
    if s.startswith("十"):
        return total + 10 + digits.get(s[1:], 0)
    if "十" in s:
        i = s.index("十")
        left = s[:i]
        right = s[i + 1 :]
        return total + digits.get(left or "一", 1) * 10 + digits.get(right, 0)
    return total + digits.get(s, 0)


def parse_articles(text: str, start_marker: str) -> dict[int, str]:
    idx = text.find(start_marker)
    if idx < 0:
        raise SystemExit(f"marker not found: {start_marker[:40]}")
    # 仅匹配行首“第×条”，避免正文中的交叉引用（如“反洗钱法第五十二条”）被拆开。
    text = text[idx:]
    if not text.startswith("第"):
        # 允许 start_marker 不在行首时，仍从该条开始
        pass
    parts = re.split(rf"(?m)^(第[{CN_NUM}]+条)(?=\s)", text)
    arts: dict[int, str] = {}
    # parts[0] may be empty; then (head, body) pairs
    i = 1 if parts and parts[0] == "" else 0
    if i == 0 and parts and not parts[0].startswith("第"):
        i = 1
    while i < len(parts) - 1:
        head, body = parts[i], parts[i + 1]
        m = re.fullmatch(rf"第([{CN_NUM}]+)条", head)
        if not m:
            i += 2
            continue
        n = cn_to_int(m.group(1))
        body = body.strip()
        body = re.split(
            r"\n+(?:第[{n}]+章|第[{n}]+节)".format(n=CN_NUM),
            body,
            maxsplit=1,
        )[0]
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        # 去掉文末页脚
        for stopper in ("【责任编辑", "新闻链接", "分享到", "备案序号", "主办单位"):
            if stopper in body:
                body = body.split(stopper, 1)[0].strip()
        if n and body:
            arts[n] = f"{head}\n{body}"
        i += 2
    return arts


def join_arts(arts: dict[int, str], lo: int, hi: int) -> str:
    missing = [i for i in range(lo, hi + 1) if i not in arts]
    if missing:
        raise SystemExit(f"missing articles {missing} in {lo}-{hi}")
    return "\n\n".join(arts[i] for i in range(lo, hi + 1))


def py_str(s: str) -> str:
    return '"""' + s.replace("\\", "\\\\").replace('"""', '\\"\\"\\"') + '"""'


def emit_statute(id: str, title: str, source: str, tags: list[str], effective: str, version: str, body: str) -> str:
    tags_lit = "[" + ", ".join(repr(t) for t in tags) + "]"
    return f"""    _statute(
        id={id!r},
        title={title!r},
        source=f"{{SRC}}{source.split('）')[-1] if False else ''}",
        tags={tags_lit},
        effective_date={effective!r},
        version={version!r},
        body={py_str(body)},
    ),
"""


HEADER = '''"""现行有效反洗钱法律、规章条款。正文取自官方公布文本，按章收录，供检索与全文展示。"""

from __future__ import annotations


def _statute(
    *,
    id: str,
    title: str,
    source: str,
    tags: list[str],
    body: str,
    effective_date: str,
    version: str,
) -> dict:
    return {
        "id": id,
        "kind": "regulation",
        "title": title,
        "source": source,
        "tags": tags,
        "body": body.strip(),
        "effective_date": effective_date,
        "expiry_date": None,
        "version": version,
        "data_note": "official-statute",
    }
'''


def emit_module(var: str, src_const: str, src_value: str, items: list[tuple]) -> str:
    chunks = [HEADER, f"\n{src_const} = {src_value!r}\n\n{var}: list[dict] = [\n"]
    for id_, title, article_span, tags, effective, version, body in items:
        tags_lit = "[" + ", ".join(repr(t) for t in tags) + "]"
        chunks.append(
            f"""    _statute(
        id={id_!r},
        title={title!r},
        source=f"{{{src_const}}}{article_span}",
        tags={tags_lit},
        effective_date={effective!r},
        version={version!r},
        body={py_str(body)},
    ),
"""
        )
    chunks.append("]\n")
    return "".join(chunks)


def main() -> None:
    aml_raw = (DUMP / "c9daec87-6aea-4855-a919-a47207a57b67.txt").read_text(encoding="utf-8")
    cdd_raw = (DUMP / "acb91c01-216c-4a8f-a483-d78583cf37b7.txt").read_text(encoding="utf-8")
    ubo_raw = (DUMP / "c631c12b-eeec-438c-bf4f-b2187940a3a2.txt").read_text(encoding="utf-8")

    aml = parse_articles(aml_raw, "第一条 为了预防洗钱活动")
    cdd = parse_articles(cdd_raw, "第一条 为了预防和遏制洗钱和恐怖融资活动，规范金融机构客户尽职调查")
    ubo = parse_articles(ubo_raw, "第一条 为了预防和遏制洗钱和恐怖融资活动，落实金融机构客户尽职调查要求")

    assert set(aml) == set(range(1, 66)), (set(range(1, 66)) - set(aml), set(aml) - set(range(1, 66)))
    assert set(cdd) == set(range(1, 53)), (set(range(1, 53)) - set(cdd), set(cdd) - set(range(1, 53)))
    assert set(ubo) == set(range(1, 42)), (set(range(1, 42)) - set(ubo), set(ubo) - set(range(1, 42)))

    aml_src = "《中华人民共和国反洗钱法》（2006年10月31日通过，2024年11月8日第十四届全国人民代表大会常务委员会第十二次会议修订，主席令第三十八号，2025年1月1日起施行）"
    cdd_src = "《金融机构客户尽职调查和客户身份资料及交易记录保存管理办法》（中国人民银行 国家金融监督管理总局 中国证券监督管理委员会令〔2025〕第11号，2026年1月1日起施行）"
    ubo_src = "《金融机构客户受益所有人识别管理办法》（中国人民银行令〔2025〕第12号，2026年1月20日起施行）"

    aml_items = [
        ("KB-AML-01", "反洗钱法·第一章 总则", "第一条至第十二条",
         ["反洗钱法", "定义", "基本原则", "金融机构", "特定非金融机构", "保密", "大额交易", "可疑交易", "法律保护"],
         "2025-01-01", "aml-2024-rev", join_arts(aml, 1, 12)),
        ("KB-AML-02", "反洗钱法·第二章 反洗钱监督管理", "第十三条至第二十六条",
         ["监督管理", "监测分析", "受益所有人", "UBO", "监督检查", "高风险国家", "自律组织"],
         "2025-01-01", "aml-2024-rev", join_arts(aml, 13, 26)),
        ("KB-AML-03", "反洗钱法·第三章 反洗钱义务", "第二十七条至第四十二条",
         ["内部控制", "尽职调查", "CDD", "匿名账户", "持续尽调", "保存十年", "大额交易", "可疑交易报告", "特别预防措施", "客户配合"],
         "2025-01-01", "aml-2024-rev", join_arts(aml, 27, 42)),
        ("KB-AML-04", "反洗钱法·第四章 反洗钱调查", "第四十三条至第四十五条",
         ["反洗钱调查", "调查通知书", "配合", "临时冻结", "四十八小时", "移送"],
         "2025-01-01", "aml-2024-rev", join_arts(aml, 43, 45)),
        ("KB-AML-05", "反洗钱法·第五章 反洗钱国际合作", "第四十六条至第五十条",
         ["国际合作", "司法协助", "对等原则", "境外金融机构", "不得擅自执行"],
         "2025-01-01", "aml-2024-rev", join_arts(aml, 46, 50)),
        ("KB-AML-06", "反洗钱法·第六章 法律责任", "第五十一条至第六十二条",
         ["法律责任", "罚款", "尽职调查", "可疑交易", "拆分交易", "负责人", "受益所有人"],
         "2025-01-01", "aml-2024-rev", join_arts(aml, 51, 62)),
        ("KB-AML-07", "反洗钱法·第七章 附则", "第六十三条至第六十五条",
         ["适用范围", "支付机构", "房地产", "会计师", "律师", "贵金属", "宝石", "施行日期"],
         "2025-01-01", "aml-2024-rev", join_arts(aml, 63, 65)),
    ]

    cdd_items = [
        ("KB-CDD-01", "尽职调查办法·第一章 总则", "第一条至第六条",
         ["尽职调查", "了解你的客户", "KYC", "受益所有人", "强化尽调", "简化尽调", "足以重现", "内部控制"],
         "2026-01-01", "cdd-2025-11", join_arts(cdd, 1, 6)),
        ("KB-CDD-02", "尽职调查办法·银行业、证券业、保险业与支付机构触发标准", "第七条至第十九条",
         ["尽职调查", "匿名账户", "五万元", "一万美元", "银行", "证券", "保险", "支付机构", "信托", "一次性金融服务"],
         "2026-01-01", "cdd-2025-11", join_arts(cdd, 7, 19)),
        ("KB-CDD-03", "尽职调查办法·身份核实、持续尽调、强化与简化", "第二十条至第三十一条",
         ["受益所有人", "核实", "风险等级", "强化尽职调查", "简化尽职调查", "无法尽调", "终止业务", "可疑交易报告", "泄密"],
         "2026-01-01", "cdd-2025-11", join_arts(cdd, 20, 31)),
        ("KB-CDD-04", "尽职调查办法·代理行、外国政要、汇款、第三方与特别预防", "第三十二条至第四十一条",
         ["代理行", "外国政要", "PEP", "跨境汇款", "第三方尽调", "特别预防措施", "高风险国家", "可疑行为"],
         "2026-01-01", "cdd-2025-11", join_arts(cdd, 32, 41)),
        ("KB-CDD-05", "尽职调查办法·资料保存、法律责任与附则", "第四十二条至第五十二条",
         ["保存十年", "交易记录", "足以重现", "存量客户", "两年", "施行", "废止"],
         "2026-01-01", "cdd-2025-11", join_arts(cdd, 42, 52)),
    ]

    ubo_items = [
        ("KB-UBO-01", "受益所有人识别办法·第一章 总则", "第一条至第七条",
         ["受益所有人", "基于风险", "合理性", "可靠性", "查询系统", "不得仅查询", "一刀切"],
         "2026-01-20", "ubo-2025-12", join_arts(ubo, 1, 7)),
        ("KB-UBO-02", "受益所有人识别办法·第二章 识别标准", "第八条至第十五条",
         ["百分之二十五", "股权", "收益权", "表决权", "实际控制", "信托", "简化识别", "豁免"],
         "2026-01-20", "ubo-2025-12", join_arts(ubo, 8, 15)),
        ("KB-UBO-03", "受益所有人识别办法·第三章 识别核实要求", "第十六条至第二十五条",
         ["所有权结构", "核实", "加强措施", "查询核对", "持续更新"],
         "2026-01-20", "ubo-2025-12", join_arts(ubo, 16, 25)),
        ("KB-UBO-04", "受益所有人识别办法·第四章 差异反馈义务", "第二十六条至第三十一条",
         ["差异报告", "重大差异", "三十个工作日", "可疑交易报告", "分别提交", "保密"],
         "2026-01-20", "ubo-2025-12", join_arts(ubo, 26, 31)),
        ("KB-UBO-05", "受益所有人识别办法·第五章 法律责任与附则", "第三十二条至第四十一条",
         ["法律责任", "反洗钱法第五十三条", "存量客户", "废止", "银发235", "施行"],
         "2026-01-20", "ubo-2025-12", join_arts(ubo, 32, 41)),
    ]

    (OUT / "knowledge_aml.py").write_text(emit_module("AML_STATUTES", "AML2024", aml_src, aml_items), encoding="utf-8")
    (OUT / "knowledge_cdd.py").write_text(emit_module("CDD_STATUTES", "CDD2025", cdd_src, cdd_items), encoding="utf-8")
    (OUT / "knowledge_ubo.py").write_text(emit_module("UBO_STATUTES", "UBO2025", ubo_src, ubo_items), encoding="utf-8")
    print("wrote", [p.name for p in (OUT / "knowledge_aml.py", OUT / "knowledge_cdd.py", OUT / "knowledge_ubo.py")])
    print("aml", len(aml), "cdd", len(cdd), "ubo", len(ubo))


if __name__ == "__main__":
    main()
