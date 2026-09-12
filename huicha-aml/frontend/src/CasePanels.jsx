import { useEffect, useState } from "react";

export function clickSource(e) {
  const raw = String(e?.raw_reference || "");
  const tx = raw
    .split(",")
    .map((s) => s.trim())
    .find((s) => /^(TX-|KB-)/.test(s));
  if (tx) return tx;
  const src = e?.source_id || "";
  if (src.includes("->")) return tx || raw.split(",")[0] || src;
  return src || raw || e?.evidence_id;
}

export function RiskFactors({ risk, onSelect }) {
  const factors = risk?.factors || [];
  if (!factors.length) return null;
  return (
    <div className="v2-panel">
      <div className="v2-hd">
        规则指标对照 · 不决定最终建议
      </div>
      <ul className="v2-factors">
        {factors.map((f) => (
          <li key={`${f.code}-${f.label}`}>
            <button type="button" className="token" onClick={() => f.evidence_ids?.[0] && onSelect(f.evidence_ids[0])}>
              {f.label}
            </button>
            <em className={f.delta < 0 ? "down" : f.delta > 0 ? "up" : ""}>
              {f.delta > 0 ? "+" : ""}
              {Number(f.delta).toFixed(2)}
            </em>
          </li>
        ))}
      </ul>
      <div className="hint">每项可点回证据。规则对照与 AI 建议不做加权合成。</div>
    </div>
  );
}

export function TxTimeline({ rows, onSelect }) {
  if (!rows?.length) return null;
  return (
    <div className="v2-panel">
      <div className="v2-hd">交易时间线</div>
      <ol className="v2-tl">
        {rows.slice(0, 16).map((t) => (
          <li key={t.tx_id}>
            <button type="button" className="token" onClick={() => onSelect(t.tx_id || t.evidence_id)}>
              {String(t.time || "").slice(5, 16)}
            </button>
            <span>
              {t.from_account} → {t.to_account}
            </span>
            <b>{t.amount != null ? Number(t.amount).toLocaleString() : ""}</b>
          </li>
        ))}
      </ol>
    </div>
  );
}

function evidenceLabel(e) {
  const src = e?.source_id || "";
  if (/^(TX-|KB-|C-|6222-|CASH-|POS-)/.test(src)) return src;
  const raw = String(e?.raw_reference || "")
    .split(",")
    .map((s) => s.trim())
    .find((s) => /^(TX-|KB-)/.test(s));
  return raw || e?.evidence_id || "";
}

function uniqueBy(items, keyFn) {
  const seen = new Set();
  const out = [];
  for (const it of items) {
    const key = keyFn(it);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(it);
  }
  return out;
}

const KIND = { enterprise: "对公", individual: "个人" };

export function CustomerCard({ customer, accountId, selected, onSelect }) {
  if (!customer?.id) return null;
  const active = selected === customer.id || selected === accountId;
  const accounts = customer.accounts?.length ? customer.accounts.join("、") : accountId || "—";
  return (
    <div
      id={`ev-${customer.id}`}
      className={`kyc-card${active ? " is-on" : ""}`}
      role="button"
      tabIndex={0}
      onClick={() => onSelect(customer.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter") onSelect(customer.id);
      }}
    >
      <div className="kyc-hd">
        <b>{customer.name || customer.id}</b>
        <code>{customer.id}</code>
      </div>
      <dl className="kyc-dl">
        <div>
          <dt>类型</dt>
          <dd>{KIND[customer.kind] || customer.kind || "—"}</dd>
        </div>
        <div>
          <dt>行业</dt>
          <dd>{customer.industry || "—"}</dd>
        </div>
        <div>
          <dt>KYC</dt>
          <dd>{customer.kyc_level || "—"}</dd>
        </div>
        <div>
          <dt>开户</dt>
          <dd>{customer.opened_at || "—"}</dd>
        </div>
        <div>
          <dt>城市</dt>
          <dd>{customer.city || "—"}</dd>
        </div>
        <div>
          <dt>账号</dt>
          <dd>
            <code>{accounts}</code>
          </dd>
        </div>
      </dl>
      {customer.summary ? <p className="kyc-sum">{customer.summary}</p> : null}
      <p className="kyc-note">合成档案摘要，不是尽调原件。开户申请、受益所有人、回访记录未入库。</p>
    </div>
  );
}

export function EvidenceLists({ graph, claims, kbHits, ablation, selected, onSelect }) {
  const items = graph || [];
  const profiles = uniqueBy(
    items.filter((e) => e.evidence_type === "CUSTOMER" || e.evidence_type === "ACCOUNT"),
    (e) => e.source_id || e.evidence_id,
  );
  const support = uniqueBy(
    items.filter((e) => e.evidence_type === "TRANSACTION"),
    (e) => e.source_id || e.raw_reference || e.evidence_id,
  );
  const counters = uniqueBy(
    items.filter((e) => e.polarity === "counter" || e.evidence_type === "COUNTER_EVIDENCE"),
    (e) => e.evidence_id || e.source_id,
  );
  const claimCounters = (claims || []).filter((c) => c.polarity === "counter");
  const rules = uniqueBy(
    [
      ...items.filter((e) => e.evidence_type === "REGULATION" || e.evidence_type === "RULE"),
      ...((kbHits || []).filter((h) => h.kind === "regulation") || []).map((h) => ({
        evidence_id: h.id,
        evidence_type: "REGULATION",
        description: h.title,
        source_id: h.id,
        raw_reference: h.id,
      })),
    ],
    (r) => r.source_id || r.evidence_id,
  );
  if (!items.length && !rules.length) return null;

  function Row({ e, extra, kind }) {
    const label = evidenceLabel(e) || extra;
    const active = selected && (selected === label || selected === e.source_id || selected === e.evidence_id);
    return (
      <div
        id={label ? `ev-${label}` : undefined}
        className={`ev ${kind || ""} ${active ? "active" : ""}`}
        role="button"
        tabIndex={0}
        onClick={() => onSelect(clickSource(e) || label)}
      >
        <code>{label}</code>
        <div>{e.description || extra || ""}</div>
      </div>
    );
  }

  return (
    <div className="v2-panel">
      <div className="v2-hd">证据分组（synthetic）</div>
      <div className="v2-hd sub">客户与账户</div>
      {profiles.slice(0, 6).map((e) => (
        <Row key={e.evidence_id} e={e} kind="profile" />
      ))}
      {!profiles.length && <div className="hint">无</div>}
      <div className="v2-hd sub">支持风险</div>
      {support.slice(0, 10).map((e) => (
        <Row key={e.evidence_id} e={e} kind="support" />
      ))}
      {!support.length && <div className="hint">无</div>}
      <div className="v2-hd sub">反向证据</div>
      {counters.slice(0, 8).map((e) => (
        <Row key={e.evidence_id} e={e} kind="counter" />
      ))}
      {claimCounters
        .filter((c) => !(c.evidence_ids || []).some((id) => counters.some((e) => (e.raw_reference || "").includes(id) || e.source_id === id)))
        .map((c) => (
          <div
            key={c.claim}
            className={`ev counter ${selected && (c.evidence_ids || []).includes(selected) ? "active" : ""}`}
            role="button"
            tabIndex={0}
            onClick={() => c.evidence_ids?.[0] && onSelect(c.evidence_ids[0])}
          >
            <code>{(c.evidence_ids || []).join("、") || "CLAIM"}</code>
            <div>{c.claim}</div>
          </div>
        ))}
      {!counters.length && !claimCounters.length && (
        <div className="hint">
          {ablation ? "本案为消融结果，未采集 Challenger 反向证据。" : "本轮未发现通过校验的反向证据。"}
        </div>
      )}
      <div className="v2-hd sub">规则依据</div>
      {rules.slice(0, 8).map((e) => (
        <Row key={e.evidence_id} e={e} kind="rule" />
      ))}
      {!rules.length && <div className="hint">无</div>}
    </div>
  );
}

const DECISION_LABEL = {
  exclude: "排除",
  observe: "继续观察",
  suggest_report: "建议上报",
};

export function JudgePanel({ judge, baseline, guardrails, validation, onSelect }) {
  if (!judge || !baseline) return null;
  const support = judge.supporting_evidence_ids || [];
  const counter = judge.contradicting_evidence_ids || [];
  return (
    <div className="ch-panel">
      <div className="v2-hd">证据约束的 AI Judge</div>
      <div className={validation?.passed ? "ch-on" : "ch-ablation"}>
        {validation?.reason || "等待证据契约校验"}；把握度为模型自评，未经概率校准。
      </div>
      <ol className="ch-flow">
        <li>
          <b>规则对照</b>
          <span>{DECISION_LABEL[baseline.conclusion] || baseline.conclusion} · {Number(baseline.score || 0).toFixed(2)}</span>
        </li>
        <li>
          <b>AI 完整建议</b>
          <span>{DECISION_LABEL[judge.disposition] || judge.disposition} · 自评 {Number(judge.confidence || 0).toFixed(2)}</span>
        </li>
        <li>
          <b>支持 / 反向 / 缺失</b>
          <span>{support.length} / {counter.length} / {(judge.missing_evidence || []).length}</span>
          <ul>
            {(judge.rationale || []).slice(0, 4).map((row, i) => (
              <li key={`${row.text}-${i}`}>
                <button type="button" className="token" onClick={() => row.evidence_ids?.[0] && onSelect(row.evidence_ids[0])}>
                  {row.text}
                </button>
                <em>{(row.evidence_ids || []).join("、")}</em>
              </li>
            ))}
          </ul>
        </li>
        <li>
          <b>政策护栏后</b>
          <span>
            {DECISION_LABEL[guardrails?.final_conclusion] || guardrails?.final_conclusion}
            {guardrails?.overridden ? " · 已覆盖模型建议" : " · 未触发结论覆盖"} · 须人工签发
          </span>
        </li>
      </ol>
      {(judge.missing_evidence || []).length > 0 && (
        <div className="hint">待补：{judge.missing_evidence.join("；")}</div>
      )}
    </div>
  );
}

export function RejectedClaims({ rows, onSelect }) {
  if (!rows?.length) return null;
  return (
    <div className="v2-panel">
      <div className="v2-hd">Skeptic 拒绝（不可签发）</div>
      {rows.slice(0, 8).map((r, i) => (
        <div
          key={`${r.claim || r.title || i}`}
          className="ev"
          role="button"
          tabIndex={0}
          onClick={() => r.evidence_ids?.[0] && onSelect(r.evidence_ids[0])}
        >
          <code>{r.validation?.reason || r.message || r.kind || "已拒绝"}</code>
          <div>{r.claim || r.title || "Judge 输出未通过证据契约"}</div>
          {r.predicate ? <div className="hint">谓词 {r.predicate}</div> : null}
        </div>
      ))}
    </div>
  );
}

export function CounterfactualBox({ cf }) {
  if (!cf) return null;
  return (
    <div className="v2-panel">
      <div className="v2-hd">关键证据反事实</div>
      <p className="hint">
        {cf.performed
          ? `移除 ${(cf.removed_evidence_ids || []).join("、")}：${DECISION_LABEL[cf.original_conclusion] || cf.original_conclusion} → ${DECISION_LABEL[cf.counterfactual_conclusion] || cf.counterfactual_conclusion || "无输出"}${cf.validated === false ? "（该轮输出未通过引用校验）" : ""}。${cf.note}`
          : cf.note || `${cf.assumption}：${cf.original} → ${cf.counterfactual}`}
      </p>
    </div>
  );
}

const SLIP_PRI = { high: "高", medium: "中", low: "低" };
const SLIP_ST = { missing: "待补", optional: "可选", satisfied: "已齐" };

export function SupplementChecklist({ data, loading, writing, onWrite }) {
  const items = data?.items || [];
  const actionable = items.filter((it) => it.status !== "satisfied");
  const [picked, setPicked] = useState(() => new Set());

  const slipKey = items.map((it) => `${it.id}:${it.status}:${it.appended}`).join("|");
  useEffect(() => {
    setPicked(new Set(items.filter((it) => it.status === "missing").map((it) => it.id)));
  }, [slipKey]);

  if (!items.length && !loading) return null;

  function toggle(id) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const selected = actionable.filter((it) => picked.has(it.id));

  return (
    <div className="slip">
      <div className="slip-hd">
        <div>
          <b>待补证</b>
          <span>签发前材料缺口 · 规则清单，不自动报送</span>
        </div>
        <em>
          缺 {data?.missing_count ?? "—"} · 要素 {data?.elements_filled ?? "—"}/{data?.elements_total ?? "—"}
        </em>
      </div>
      {loading && !items.length ? <div className="hint">正在对照案件要素…</div> : null}
      <ul className="slip-list">
        {items.map((it) => {
          const locked = it.status === "satisfied";
          const on = picked.has(it.id);
          return (
            <li key={it.id} className={`slip-row is-${it.status} is-${it.priority}${on ? " is-on" : ""}`}>
              <label className="slip-check">
                <input
                  type="checkbox"
                  disabled={locked || writing}
                  checked={on}
                  onChange={() => toggle(it.id)}
                />
                <i />
              </label>
              <div className="slip-body">
                <div className="slip-line">
                  <abbr className="slip-seal">{it.category}</abbr>
                  <strong>{it.title}</strong>
                  <small className={`slip-pri is-${it.priority}`}>{SLIP_PRI[it.priority] || it.priority}</small>
                  <small className={`slip-st is-${it.status}`}>
                    {it.appended ? "已写入" : SLIP_ST[it.status] || it.status}
                  </small>
                </div>
                <p title={`${it.reason} 怎么补：${it.suggested_action}`}>
                  {it.reason} <span className="slip-how">怎么补：{it.suggested_action}</span>
                </p>
              </div>
            </li>
          );
        })}
      </ul>
      <div className="slip-ft">
        <button
          type="button"
          className="slip-write"
          disabled={!selected.length || writing}
          onClick={() => onWrite?.(selected.map((it) => it.id))}
        >
          {writing ? "写入中…" : `写入草稿备注${selected.length ? `（${selected.length}）` : ""}`}
        </button>
        <span>勾选后写入调查员意见，便于签发或「修改后采纳」时一并带上。</span>
        {String(data?.human_note || "").includes("【补证清单】") ? (
          <em className="slip-echo">已落入下方草稿备注，不自动报送。</em>
        ) : null}
      </div>
    </div>
  );
}

export function RegulationBox({ cites, onSelect }) {
  const rows = cites || [];
  if (!rows.length) return null;
  return (
    <div className="v2-panel">
      <div className="v2-hd">法规依据（转述，须点开核对）</div>
      {rows.map((r) => (
        <div key={r.regulation_id || r.title} className="ev" onClick={() => r.regulation_id && onSelect(r.regulation_id)}>
          <code>{r.regulation_id || "无"}</code> {r.article} {r.title}
          <div className="hint">{r.source || "未检索到足够法规依据。"}</div>
        </div>
      ))}
    </div>
  );
}
