import { useEffect, useMemo, useRef, useState } from "react";
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
  if (kind === "watch") return "#c8161d";
  if (kind === "center") return "#0a1628";
  if (kind === "channel") return "#0f7b4a";
  return "#1b4f8a";
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

export default function Graph({ graph, selected, onSelect, formatYuan = (n) => String(n) }) {
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  const nodeKey = nodes.map((n) => n.id).join("|");
  const edgeKey = edges.map((e) => `${e.source}>${e.target}`).join("|");
  const seed = useMemo(() => initialLayout(nodes, edges), [nodeKey, edgeKey]);
  const [pos, setPos] = useState(seed);
  const [hover, setHover] = useState("");
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

  return (
    <div className="graph">
      <div className="graph-toolbar">
        <span>拖动节点展开路径，点击回溯流水</span>
        <button type="button" className="graph-reset" onClick={() => setPos(seed)}>
          复位
        </button>
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
            <path d="M0,0 L7,3.2 L0,6.4 Z" fill="#c8161d" />
          </marker>
          <radialGradient id="orbit" cx="50%" cy="46%" r="48%">
            <stop offset="0%" stopColor="#1d4f86" stopOpacity="0.10" />
            <stop offset="100%" stopColor="#1d4f86" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect width={GRAPH_W} height={GRAPH_H} fill="url(#orbit)" />
        <ellipse cx={GRAPH_W / 2} cy={GRAPH_H * 0.46} rx="118" ry="78" fill="none" stroke="#d5deea" strokeDasharray="3 5" />
        <ellipse cx={GRAPH_W / 2} cy={GRAPH_H * 0.46} rx="72" ry="46" fill="none" stroke="#e4ebf3" strokeDasharray="2 6" />
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
                stroke={hot ? "#c8161d" : "#94a3b8"}
                strokeWidth={hot ? thick + 0.8 : thick}
                markerEnd={hot ? "url(#arr-hot)" : "url(#arr)"}
              />
              {e.amount != null && (
                <text x={mx} y={my - 6} textAnchor="middle" fill={hot ? "#9f1239" : "#64748b"} fontSize="8">
                  {formatYuan(e.amount)}
                  {e.count > 1 ? ` · ${e.count}笔` : ""}
                </text>
              )}
            </g>
          );
        })}
        {Object.values(layout).map((n) => {
          const hot = nodeHot(n, selected, hotEdges) || n.id === hover;
          const cap = nodeCaption(n);
          const r = nodeRadius(n, hot);
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
                stroke={hot ? "#c8161d" : "#fff"}
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
