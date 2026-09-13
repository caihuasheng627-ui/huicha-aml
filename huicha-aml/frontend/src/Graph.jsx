import { useEffect, useMemo, useRef, useState } from "react";
import { Modal } from "antd";
import { GRAPH_H, GRAPH_W, initialLayout, nodeCaption } from "./graphLayout.js";

function isChannelToken(id, prefix) {
  return id === `${prefix}-AGG` || String(id).startsWith(`${prefix}-`);
}

export function edgeHot(e, selected) {
  if (!selected) return false;
  if (e.id === selected || (e.tx_ids || []).includes(selected)) return true;
  if (e.source === selected || e.target === selected) return true;
  if (isChannelToken(selected, "CASH") && (e.source === "CASH-AGG" || e.target === "CASH-AGG")) return true;
  if (isChannelToken(selected, "POS") && (e.source === "POS-AGG" || e.target === "POS-AGG")) return true;
  return false;
}

export function nodeHot(n, selected, hotEdges) {
  if (!selected) return false;
  if (n.id === selected) return true;
  if (isChannelToken(selected, "CASH") && n.id === "CASH-AGG") return true;
  if (isChannelToken(selected, "POS") && n.id === "POS-AGG") return true;
  return hotEdges.some((e) => e.source === n.id || e.target === n.id);
}

function nodeFill(kind) {
  if (kind === "watch") return "#b42318";
  if (kind === "center") return "#2b3038";
  if (kind === "channel") return "#2d6a4f";
  return "#3a5a7c";
}

function nodeRadius(n, hot) {
  if (n.kind === "center") return 16;
  return hot ? 12 : 10;
}

function shorten(a, b, r1, r2) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  return {
    x1: a.x + (dx / len) * r1,
    y1: a.y + (dy / len) * r1,
    x2: b.x - (dx / len) * r2,
    y2: b.y - (dy / len) * r2,
  };
}

function clientToSvg(svg, ev) {
  const pt = svg.createSVGPoint();
  pt.x = ev.clientX;
  pt.y = ev.clientY;
  const ctm = svg.getScreenCTM();
  if (!ctm) return { x: 0, y: 0 };
  const p = pt.matrixTransform(ctm.inverse());
  return { x: p.x, y: p.y };
}

export default function Graph({ graph, selected, onSelect, riskFactors = [], formatYuan = (n) => String(n) }) {
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  const nodeKey = nodes.map((n) => n.id).join("|");
  const edgeKey = edges.map((e) => `${e.source}>${e.target}`).join("|");
  const seed = useMemo(() => initialLayout(nodes, edges), [nodeKey, edgeKey]);
  const [pos, setPos] = useState(seed);
  const [hover, setHover] = useState("");
  const [expanded, setExpanded] = useState(false);
  const drag = useRef(null);
  const svgRef = useRef(null);

  useEffect(() => {
    setPos(seed);
  }, [seed]);

  const layout = useMemo(() => {
    const next = {};
    nodes.forEach((n) => {
      next[n.id] = { ...n, ...(pos[n.id] || seed[n.id] || { x: GRAPH_W / 2, y: GRAPH_H / 2 }) };
    });
    return next;
  }, [nodes, pos, seed]);

  const hotEdges = edges.filter((e) => edgeHot(e, selected) || edgeHot(e, hover));
  const maxAmt = Math.max(1, ...edges.map((e) => Number(e.amount) || 0));
  const focus = selected && layout[selected] ? layout[selected] : hover && layout[hover] ? layout[hover] : null;

  function onPointerDown(ev, id) {
    ev.preventDefault();
    ev.stopPropagation();
    const svg = svgRef.current;
    if (!svg) return;
    const p = clientToSvg(svg, ev);
    const n = layout[id];
    drag.current = { id, dx: p.x - n.x, dy: p.y - n.y, moved: false, x0: p.x, y0: p.y };
    ev.currentTarget.setPointerCapture(ev.pointerId);
  }

  function onPointerMove(ev) {
    if (!drag.current || !svgRef.current) return;
    const p = clientToSvg(svgRef.current, ev);
    const d = drag.current;
    if (Math.hypot(p.x - d.x0, p.y - d.y0) > 3) d.moved = true;
        const x = Math.max(22, Math.min(GRAPH_W - 22, p.x - d.dx));
        const y = Math.max(22, Math.min(GRAPH_H - 28, p.y - d.dy));
    setPos((prev) => ({ ...prev, [d.id]: { ...(prev[d.id] || layout[d.id]), x, y } }));
  }

  function onPointerUp(id) {
    const d = drag.current;
    drag.current = null;
    if (!d?.moved) onSelect?.(id);
  }

  function renderGraph() {
    return (
      <div className={`graph${expanded ? " graph-expanded" : ""}`}>
        <div className="graph-toolbar">
          <span>拖动节点展开路径，点击回溯流水</span>
          <div className="graph-actions">
            <button type="button" className="graph-reset" onClick={() => setPos(seed)}>
              复位
            </button>
            {!expanded && (
              <button type="button" className="graph-expand" onClick={() => setExpanded(true)}>
                放大查看
              </button>
            )}
          </div>
        </div>
      <svg
        ref={svgRef}
        className="graph-live"
        viewBox={`0 0 ${GRAPH_W} ${GRAPH_H}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerMove={onPointerMove}
      >
        <defs>
          <marker id="arr" markerWidth="7" markerHeight="7" refX="6" refY="3.2" orient="auto">
            <path d="M0,0 L7,3.2 L0,6.4 Z" fill="#7b8ea6" />
          </marker>
          <marker id="arr-hot" markerWidth="7" markerHeight="7" refX="6" refY="3.2" orient="auto">
            <path d="M0,0 L7,3.2 L0,6.4 Z" fill="#b42318" />
          </marker>
        </defs>
        <rect width={GRAPH_W} height={GRAPH_H} fill="#f4f5f7" />
        {edges.map((e) => {
          const a = layout[e.source];
          const b = layout[e.target];
          if (!a || !b) return null;
          const hot = edgeHot(e, selected) || edgeHot(e, hover);
          const ra = nodeRadius(a, nodeHot(a, selected, hotEdges) || nodeHot(a, hover, hotEdges));
          const rb = nodeRadius(b, nodeHot(b, selected, hotEdges) || nodeHot(b, hover, hotEdges));
          const s = shorten(a, b, ra + 1, rb + 2);
          const mx = (s.x1 + s.x2) / 2;
          const my = (s.y1 + s.y2) / 2;
          const thick = 1 + (Number(e.amount) / maxAmt) * 2.4;
          const edgeFactors = expanded
            ? riskFactors.filter((factor) =>
                (factor.evidence_ids || []).some((id) => e.tx_ids?.includes(id) || e.id === id),
              )
            : [];
          return (
            <g
              key={`${e.source}-${e.target}-${e.id}`}
              className={hot ? "is-hot" : ""}
              onClick={() => onSelect?.(e.tx_ids?.[0] || e.id)}
              style={{ cursor: "pointer" }}
            >
              <line
                x1={s.x1}
                y1={s.y1}
                x2={s.x2}
                y2={s.y2}
                stroke={hot ? "#b42318" : "#94a3b8"}
                strokeWidth={hot ? thick + 0.8 : thick}
                markerEnd={hot ? "url(#arr-hot)" : "url(#arr)"}
              />
              {e.amount != null && (
                <text x={mx} y={my - 6} textAnchor="middle" fill={hot ? "#9f1239" : "#64748b"} fontSize="8">
                  {formatYuan(e.amount)}
                  {e.count > 1 ? ` · ${e.count}笔` : ""}
                </text>
              )}
              {edgeFactors.slice(0, 2).map((factor, index) => {
                const label = `疑点 ${factor.label || factor.code || "规则命中"}`;
                const width = Math.min(132, Math.max(48, label.length * 7 + 12));
                return (
                  <g
                    key={`${e.id}-${factor.code || index}`}
                    className="graph-callout graph-edge-callout"
                    transform={`translate(${mx - width / 2} ${my + 8 + index * 15})`}
                    pointerEvents="none"
                  >
                    <rect width={width} height="13" rx="2" />
                    <text x={width / 2} y="9" textAnchor="middle">
                      {label.slice(0, 20)}
                    </text>
                  </g>
                );
              })}
            </g>
          );
        })}
        {Object.values(layout).map((n) => {
          const hot = nodeHot(n, selected, hotEdges) || n.id === hover;
          const cap = nodeCaption(n);
          const r = nodeRadius(n, hot);
          const nodeFlags = [];
          if (expanded && n.kind === "watch") nodeFlags.push("名单命中");
          if (
            expanded &&
            String(n.id).startsWith("UNK-") &&
            riskFactors.some((factor) => factor.code === "unregistered-counterparty")
          ) {
            nodeFlags.push("未登记对手");
          }
          return (
            <g
              key={n.id}
              className={`graph-node${hot ? " is-hot" : ""}${n.kind === "center" ? " is-center" : ""}`}
              onPointerDown={(ev) => onPointerDown(ev, n.id)}
              onPointerMove={onPointerMove}
              onPointerUp={() => onPointerUp(n.id)}
              onPointerCancel={() => {
                drag.current = null;
              }}
              onPointerEnter={() => setHover(n.id)}
              onPointerLeave={() => setHover((h) => (h === n.id ? "" : h))}
            >
              <title>{`${n.label || n.id} · ${n.id}`}</title>
              {hot && <circle cx={n.x} cy={n.y} r={r + 6} fill={nodeFill(n.kind)} opacity="0.12" />}
              <circle
                cx={n.x}
                cy={n.y}
                r={r}
                fill={nodeFill(n.kind)}
                stroke={hot ? "#b42318" : "#fff"}
                strokeWidth="2"
              />
              <text x={n.x} y={n.y + r + 12} textAnchor="middle" fill="#1c2838" fontSize="10" fontWeight="650">
                {cap.primary}
              </text>
              {cap.secondary ? (
                <text x={n.x} y={n.y + r + 23} textAnchor="middle" fill="#64748b" fontSize="8">
                  {cap.secondary}
                </text>
              ) : null}
              {nodeFlags.length > 0 && (
                <g className="graph-callout graph-node-callout" pointerEvents="none">
                  <line x1={n.x + r} y1={n.y - r} x2={n.x + r + 8} y2={n.y - r - 8} />
                  <rect x={n.x + r + 7} y={n.y - r - 22} width="68" height="14" rx="2" />
                  <text x={n.x + r + 41} y={n.y - r - 12} textAnchor="middle">
                    {nodeFlags[0]}
                  </text>
                </g>
              )}
            </g>
          );
        })}
      </svg>
      <div className="graph-legend" aria-hidden="true">
        <span>
          <i className="dot center" />
          主体
        </span>
        <span>
          <i className="dot peer" />
          对手方
        </span>
        <span>
          <i className="dot channel" />
          渠道
        </span>
        <span>
          <i className="dot watch" />
          关注名单
        </span>
      </div>
      <div className="graph-focus">
        {focus ? (
          <>
            <code>{focus.id}</code>
            <span>{focus.label || "未命名账户"}</span>
          </>
        ) : (
          <span>资金沿箭头流动。同名过桥账户用编号区分，可拖开重叠节点。</span>
        )}
      </div>
      </div>
    );
  }

  return (
    <>
      {!expanded && renderGraph()}
      <Modal
        title="案例回溯 · 关系图谱"
        open={expanded}
        onCancel={() => setExpanded(false)}
        footer={null}
        destroyOnClose
        width={1120}
        centered
      >
        {expanded && renderGraph()}
      </Modal>
    </>
  );
}
