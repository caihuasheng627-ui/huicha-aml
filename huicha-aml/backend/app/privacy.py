from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PrivacyMap:
    """进模脱敏：姓名/账号 → 占位符；出模还原。合成数据也走同一路径，方便答辩。"""

    name_to_mask: dict[str, str] = field(default_factory=dict)
    mask_to_name: dict[str, str] = field(default_factory=dict)
    acct_to_mask: dict[str, str] = field(default_factory=dict)
    mask_to_acct: dict[str, str] = field(default_factory=dict)
    _name_i: int = 0
    _acct_i: int = 0

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
        if acct.startswith(("CASH-", "POS-", "RELATIVE-")):
            # 渠道聚合名可保留语义，不发真实对手户名
            return acct
        if acct not in self.acct_to_mask:
            self._acct_i += 1
            mask = f"ACCOUNT_{self._acct_i:03d}"
            self.acct_to_mask[acct] = mask
            self.mask_to_acct[mask] = acct
        return self.acct_to_mask[acct]

    def mask_text(self, text: str) -> str:
        if not text:
            return text
        out = text
        # 先替换较长账号/姓名，避免部分命中
        for raw, mask in sorted(self.acct_to_mask.items(), key=lambda x: -len(x[0])):
            out = out.replace(raw, mask)
        for raw, mask in sorted(self.name_to_mask.items(), key=lambda x: -len(x[0])):
            out = out.replace(raw, mask)
        return out

    def unmask_text(self, text: str) -> str:
        if not text:
            return text
        out = text
        for mask, raw in sorted(self.mask_to_acct.items(), key=lambda x: -len(x[0])):
            out = out.replace(mask, raw)
        for mask, raw in sorted(self.mask_to_name.items(), key=lambda x: -len(x[0])):
            out = out.replace(mask, raw)
        return out

    def mask_obj(self, obj):
        if isinstance(obj, str):
            return self.mask_text(obj)
        if isinstance(obj, list):
            return [self.mask_obj(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self.mask_obj(v) for k, v in obj.items()}
        return obj

    def build_from_bundle(self, bundle: dict) -> None:
        c = bundle.get("customer") or {}
        if c.get("name"):
            self.register_name(c["name"])
        alert = bundle.get("alert") or {}
        if alert.get("account_id"):
            self.register_account(alert["account_id"])
        for t in bundle.get("transactions") or []:
            self.register_account(t.get("from_account", ""))
            self.register_account(t.get("to_account", ""))
        for n in (bundle.get("graph") or {}).get("nodes") or []:
            lab = n.get("label") or ""
            if lab and not lab.startswith(("现金", "POS")):
                self.register_name(lab)
            if n.get("id"):
                self.register_account(n["id"])
        for h in bundle.get("watch_hits") or []:
            if h.get("name"):
                self.register_name(h["name"])
            if h.get("account_id"):
                self.register_account(h["account_id"])
