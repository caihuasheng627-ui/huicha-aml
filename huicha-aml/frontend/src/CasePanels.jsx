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
        风险因子 · {risk.risk_level} · {risk.recommendation_label}
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
      <div className="hint">每项可点证据编号。AI 建议不是监管结论，须人签。</div>
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

export function EvidenceLists({ graph, claims, kbHits, ablation, selected, onSelect }) {
  const items = graph || [];
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

export function ChallengerPanel({ run, onSelect }) {
  if (!run) return null;
  const bound = Number(run.delta_bound ?? 0.15);
  const delta = Number(run.llm_delta ?? 0);
  const sign = delta > 0 ? "+" : "";
  return (
    <div className="ch-panel">
      <div className="v2-hd">AI反向质询（Challenger）</div>
      {run.ablation ? (
        <div className="ch-ablation">
          本案为消融结果。生成时未启用 AI 反向质询，当前展示的是 Challenger OFF 的历史调查结果。顶部开关只影响下一次「按当前策略重跑」。
        </div>
      ) : (
        <div className="ch-on">
          AI反向质询已参与本次调查。可提出反向证据，但不能绕过规则直接改最终决策；最终仍须人工签发。
        </div>
      )}
      <ol className="ch-flow">
        <li>
          <b>初始判断</b>
          <span>
            规则风险 {Number(run.initial_score ?? 0).toFixed(2)} · {run.initial_label || "—"}
          </span>
        </li>
        <li>
          <b>反向质询</b>
          <span>Challenger 主动寻找：支持当前判断的证据、能够削弱当前判断的反向证据、以及可解释当前交易的正常业务原因。</span>
          {(run.claims || []).length > 0 && (
            <ul>
              {run.claims.slice(0, 4).map((c) => (
                <li key={c.claim}>
                  <button type="button" className="token" onClick={() => c.evidence_ids?.[0] && onSelect(c.evidence_ids[0])}>
                    {c.claim}
                  </button>
                  <em className={Number(c.delta) < 0 ? "down" : Number(c.delta) > 0 ? "up" : ""}>
                    {Number(c.delta) > 0 ? "+" : ""}
                    {Number(c.delta).toFixed(2)}
                  </em>
                </li>
              ))}
            </ul>
          )}
        </li>
        <li>
          <b>证据验证</b>
          <span>
            有效证据 {(run.support_ids || []).length} 条 · 反向证据 {(run.counter_ids || []).length} 条 · 无效证据 {(run.invalid_ids || []).length} 条
            {run.validator?.passed === false ? " · Challenger 输出未通过证据校验，Δ 已置 0" : ""}
            {run.delta_clamped ? " · 合计 Δ 已夹紧到 ±0.15" : ""}
          </span>
        </li>
        <li>
          <b>风险调整</b>
          <span>
            规则先验 {Number(run.rule_prior ?? 0) > 0 ? "+" : ""}
            {Number(run.rule_prior ?? 0).toFixed(2)} · Challenger Δ {sign}
            {delta.toFixed(2)} · 允许范围 [{-bound.toFixed(2)}, +{bound.toFixed(2)}]
          </span>
        </li>
        <li>
          <b>最终判断</b>
          <span>
            最终风险 {Number(run.final_score ?? 0).toFixed(2)} · {run.final_label || "—"} · 须人工签发
          </span>
        </li>
      </ol>
    </div>
  );
}

export function VerifiedClaims({ rows, onSelect }) {
  const kept = (rows || []).filter((r) => r.validation?.score_kind === "predicate_verified");
  if (!kept.length) return null;
  return (
    <div className="v2-panel">
      <div className="v2-hd">已核验谓词（数据复核为真，才进分）</div>
      {kept.map((r, i) => (
        <div
          key={`${r.predicate || "p"}-${r.claim || r.title || i}`}
          className="ev"
          role="button"
          tabIndex={0}
          onClick={() => r.evidence_ids?.[0] && onSelect(r.evidence_ids[0])}
        >
          <code>
            {r.predicate} · Δ{Number(r.delta || 0) > 0 ? "+" : ""}
            {Number(r.delta || 0).toFixed(2)}
          </code>
          <div>{r.claim || r.title}</div>
          <div className="hint">{(r.validation?.reason || "") + " · " + (r.evidence_ids || []).join("、")}</div>
        </div>
      ))}
    </div>
  );
}

export function RejectedClaims({ rows, onSelect }) {
  if (!rows?.length) return null;
  return (
    <div className="v2-panel">
      <div className="v2-hd">Validator 拒绝（未进分）</div>
      {rows.slice(0, 8).map((r, i) => (
        <div
          key={`${r.claim || r.title || i}`}
          className="ev"
          role="button"
          tabIndex={0}
          onClick={() => r.evidence_ids?.[0] && onSelect(r.evidence_ids[0])}
        >
          <code>{r.validation?.reason || "已拒绝"}</code>
          <div>{r.claim || r.title}</div>
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
      <div className="v2-hd">反事实（规则重算）</div>
      <p className="hint">
        {cf.assumption}：{cf.original} → {cf.counterfactual}（差 {cf.difference}）
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
                <p>{it.reason}</p>
                <p className="slip-how">怎么补：{it.suggested_action}</p>
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
