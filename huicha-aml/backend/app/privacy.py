from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

POLICY_VERSION = "privacy_v2"

# 演示账号形态；真实核心号段不会进本仓库，但仍作为出站硬拦截。
ACCOUNT_TOKEN = re.compile(r"6222-[A-Z0-9\-]+")
_CUSTOMER_ID = re.compile(r"^(C-[A-Z0-9]+|P-\d+)$")
_KEEP_PREFIXES = ("CASH-", "POS-", "RELATIVE-", "UNK-")
_ID_KEEP_PREFIXES = ("TX-", "ALT-", "EV-", "KB-", "CLIENT_", "ACCOUNT_", "CUST_")
# 进模时丢掉的准标识，分析不依赖这些字段。
_DROP_KEYS = frozenset({"city", "phone", "mobile", "id_number", "id_card", "legal_id"})


class PrivacyLeakError(RuntimeError):
    """出站载荷仍含登记过的姓名/账号，拒绝调用模型。"""


def _as_text(obj) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False)


def inspect_outbound(messages) -> None:
    """HTTP 出站前门：未脱敏的 6222- 账号一律拦截。"""
    blob = _as_text(messages)
    hit = ACCOUNT_TOKEN.search(blob)
    if hit:
        raise PrivacyLeakError(f"出站消息含账号形态 token {hit.group(0)}，已拦截")


@dataclass
class PrivacyMap:
    """进模脱敏：姓名/账号/客户号 → 占位符；出模还原。合成数据也走同一路径，方便答辩。"""

    name_to_mask: dict[str, str] = field(default_factory=dict)
    mask_to_name: dict[str, str] = field(default_factory=dict)
    acct_to_mask: dict[str, str] = field(default_factory=dict)
    mask_to_acct: dict[str, str] = field(default_factory=dict)
    customer_to_mask: dict[str, str] = field(default_factory=dict)
    mask_to_customer: dict[str, str] = field(default_factory=dict)
    _name_i: int = 0
    _acct_i: int = 0
    _cust_i: int = 0
    egress_calls: int = 0

    def register_name(self, name: str) -> str:
        name = (name or "").strip()
        if not name:
            return name
        if name not in self.name_to_mask:
            self._name_i += 1
            mask = f"CLIENT_{self._name_i:03d}"
            self.name_to_mask[name] = mask
            self.mask_to_name[mask] = name
        return self.name_to_mask[name]

    def register_account(self, acct: str) -> str:
        acct = (acct or "").strip()
        if not acct:
            return acct
        if acct.startswith(_KEEP_PREFIXES):
            # 渠道聚合名可保留语义，不发真实对手户名
            return acct
        if acct.startswith("UNK-"):
            return acct
        if _CUSTOMER_ID.fullmatch(acct):
            return self.register_customer_id(acct)
        if acct.startswith(_ID_KEEP_PREFIXES):
            return acct
        if acct not in self.acct_to_mask:
            self._acct_i += 1
            mask = f"ACCOUNT_{self._acct_i:03d}"
            self.acct_to_mask[acct] = mask
            self.mask_to_acct[mask] = acct
        return self.acct_to_mask[acct]

    def register_customer_id(self, cid: str) -> str:
        cid = (cid or "").strip()
        if not cid:
            return cid
        if cid.startswith(_KEEP_PREFIXES) or cid.startswith(_ID_KEEP_PREFIXES):
            return cid
        if cid not in self.customer_to_mask:
            self._cust_i += 1
            mask = f"CUST_{self._cust_i:03d}"
            self.customer_to_mask[cid] = mask
            self.mask_to_customer[mask] = cid
        return self.customer_to_mask[cid]

    def _apply(self, text: str, mapping: dict[str, str]) -> str:
        out = text
        for raw, mask in sorted(mapping.items(), key=lambda x: -len(x[0])):
            if raw:
                out = out.replace(raw, mask)
        return out

    def mask_text(self, text: str) -> str:
        if not text:
            return text
        out = text
        # 先替换较长账号/姓名，避免部分命中
        out = self._apply(out, self.acct_to_mask)
        out = self._apply(out, self.name_to_mask)
        out = self._apply(out, self.customer_to_mask)
        return out

    def unmask_text(self, text: str) -> str:
        if not text:
            return text
        out = text
        for mapping in (self.mask_to_acct, self.mask_to_name, self.mask_to_customer):
            out = self._apply(out, mapping)
        return out

    def mask_obj(self, obj):
        if isinstance(obj, str):
            return self.mask_text(obj)
        if isinstance(obj, list):
            return [self.mask_obj(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self.mask_obj(v) for k, v in obj.items() if k not in _DROP_KEYS}
        return obj

    def raw_secrets(self) -> list[str]:
        vals = [*self.name_to_mask, *self.acct_to_mask, *self.customer_to_mask]
        return [v for v in vals if v and len(v) >= 2]

    def leaks_in(self, obj) -> list[str]:
        blob = _as_text(obj)
        found: list[str] = []
        for raw in sorted(self.raw_secrets(), key=len, reverse=True):
            if raw in blob:
                found.append(raw)
        if ACCOUNT_TOKEN.search(blob):
            found.append("account-token")
        return list(dict.fromkeys(found))

    def assert_clean(self, obj) -> None:
        leaks = self.leaks_in(obj)
        if leaks:
            preview = "、".join(leaks[:3])
            raise PrivacyLeakError(f"进模载荷含未脱敏字段：{preview}")

    def prepare_for_llm(self, obj):
        """字段级脱敏 + 出站检漏。工作台原文不走这里。"""
        masked = self.mask_obj(obj)
        self.assert_clean(masked)
        self.egress_calls += 1
        return masked

    def receipt(self) -> dict:
        return {
            "policy": POLICY_VERSION,
            "masked_names": len(self.name_to_mask),
            "masked_accounts": len(self.acct_to_mask),
            "masked_customer_ids": len(self.customer_to_mask),
            "egress_calls": self.egress_calls,
            "leaks_blocked": 0,
            "note": "仅 LLM 出站脱敏；工作台与签发稿为受控明文，SQLite 不加密",
        }

    def build_from_bundle(self, bundle: dict) -> None:
        c = bundle.get("customer") or {}
        if c.get("id"):
            self.register_customer_id(c["id"])
        if c.get("name"):
            self.register_name(c["name"])
        alert = bundle.get("alert") or {}
        if alert.get("account_id"):
            self.register_account(alert["account_id"])
        if alert.get("customer_id"):
            self.register_customer_id(alert["customer_id"])
        for t in bundle.get("transactions") or []:
            self.register_account(t.get("from_account", ""))
            self.register_account(t.get("to_account", ""))
        for n in (bundle.get("graph") or {}).get("nodes") or []:
            lab = n.get("label") or ""
            if lab and not lab.startswith(("现金", "POS")):
                self.register_name(lab)
            nid = n.get("id") or ""
            if nid:
                self.register_account(nid)
        for h in bundle.get("watch_hits") or []:
            if h.get("name"):
                self.register_name(h["name"])
            if h.get("account_id"):
                self.register_account(h["account_id"])
            if h.get("customer_id"):
                self.register_customer_id(h["customer_id"])
