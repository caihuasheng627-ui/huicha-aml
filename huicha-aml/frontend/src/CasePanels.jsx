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

export function ApproachComparison({ validation, guardrails, factIssues }) {
  const evidenceGate = validation?.passed ? "已通过本案证据校验" : "未通过则阻断建议";
  const policyGate = guardrails?.overridden ? "护栏已覆盖模型建议" : "护栏检查未覆盖结论";
  const factGate = factIssues?.length ? "事实回查失败，禁止签发" : "事实回查通过后可人工签发";
  const rows = [
    ["结论来源", "直接生成结论", "只在本轮工具证据范围内给建议"],
    ["事实依据", "依赖上下文，难以逐项回溯", "理由绑定证据编号，可点击回到原始交易"],
    ["错误控制", "主要依赖人工阅读发现问题", `${evidenceGate}；跨案或伪造引用不进结论`],
    ["风险边界", "可能把模型输出当成最终结果", `${policyGate}；${factGate}`],
    ["最终动作", "容易形成自动化闭环", "AI 只能生成草稿，人工身份签发且写入审计"],
  ];
  return (
    <section className="approach-compare" aria-label="普通 AI 与循证慧查对照">
      <div className="approach-compare-hd">
        <div>
          <b>普通 AI vs 循证慧查</b>
          <span>同样使用模型，控制边界完全不同</span>
        </div>
        <em>本案实时状态</em>
      </div>
      <div className="approach-compare-grid">
        <div className="approach-col approach-col-basic">
          <strong>普通 AI</strong>
          <small>生成优先</small>
        </div>
        <div className="approach-col approach-col-huicha">
          <strong>循证慧查</strong>
          <small>证据约束 + 人工负责</small>
        </div>
        {rows.map(([label, basic, huicha]) => (
          <div className="approach-row" key={label}>
            <b>{label}</b>
            <span className="approach-basic">{basic}</span>
            <span className="approach-huicha">{huicha}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function materialGaps(list) {
  return (list || []).filter((t) => /[\u4e00-\u9fff]/.test(t) && !/^(EV|TX|KB|ALT)-/i.test(String(t).trim()));
}

export function JudgePanel({ judge, baseline, guardrails, validation, onSelect }) {
  if (!judge || !baseline) return null;
  const support = judge.supporting_evidence_ids || [];
  const counter = judge.contradicting_evidence_ids || [];
  const missing = materialGaps(judge.missing_evidence);
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
          <span>{support.length} / {counter.length} / {missing.length}</span>
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
      {missing.length > 0 && <div className="hint">待补：{missing.join("；")}</div>}
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
  const items = (data?.items || []).filter((it) => !/^AI-GAP-/.test(it.id || "") || materialGaps([it.title]).length);
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
  const [openId, setOpenId] = useState("");
  if (!rows.length) return null;
  return (
    <div className="v2-panel">
      <div className="v2-hd">法规依据（转述，须点开核对）</div>
      {rows.map((r, i) => {
        const key = r.regulation_id || r.title || String(i);
        const opened = openId === key;
        return (
          <div key={key} className={`reg-cite${opened ? " is-open" : ""}`}>
            <button
              type="button"
              className="reg-cite-hd"
              aria-expanded={opened}
              onClick={() => setOpenId(opened ? "" : key)}
            >
              <code>{r.regulation_id || "无编号"}</code>
              <span className="reg-cite-title">
                {r.article ? `${r.article} ` : ""}
                {r.title}
              </span>
              <i className="reg-cite-caret">{opened ? "收起" : "展开"}</i>
            </button>
            <div className="hint reg-cite-src">{r.source || "未检索到足够法规依据，禁止编造条款。"}</div>
            {opened && (
              <div className="reg-cite-body">
                <p>{r.evidence || "本条没有可展示的转述正文。"}</p>
                <dl className="reg-cite-meta">
                  <div>
                    <dt>条款出处</dt>
                    <dd>{r.source || "—"}</dd>
                  </div>
                  <div>
                    <dt>生效日 / 案发基准日</dt>
                    <dd>
                      {r.effective_date || "—"} / {r.as_of || "—"}
                    </dd>
                  </div>
                </dl>
                <div className="reg-cite-ft">
                  <span>本文为公开要求转述，不是法规全文，签发前须回原文核对。</span>
                  {r.regulation_id && (
                    <button type="button" className="reg-cite-jump" onClick={() => onSelect(r.regulation_id)}>
                      在右栏知识库定位
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
