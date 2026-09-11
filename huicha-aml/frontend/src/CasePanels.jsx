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

export function EvidenceLists({ graph, claims, onSelect }) {
  const items = graph || [];
  const support = items.filter((e) => e.polarity !== "counter").slice(0, 12);
  const counters = (claims || []).filter((c) => c.polarity === "counter");
  if (!items.length) return null;
  return (
    <div className="v2-panel">
      <div className="v2-hd">Evidence Graph（synthetic）</div>
      {support.map((e) => (
        <div
          key={e.evidence_id}
          className="ev"
          role="button"
          tabIndex={0}
          onClick={() => onSelect(clickSource(e))}
        >
          <code>
            {e.evidence_id} · {e.evidence_type}
          </code>
          <div>{e.description}</div>
        </div>
      ))}
      {counters.length > 0 && (
        <>
          <div className="v2-hd">Counter Evidence</div>
          {counters.map((c) => (
            <div
              key={c.claim}
              className="ev"
              role="button"
              tabIndex={0}
              onClick={() => c.evidence_ids?.[0] && onSelect(c.evidence_ids[0])}
            >
              <div>{c.claim}</div>
              <div className="hint">{(c.evidence_ids || []).join("、")}</div>
            </div>
          ))}
        </>
      )}
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
