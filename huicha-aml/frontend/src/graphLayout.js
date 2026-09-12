export const GRAPH_W = 400;
export const GRAPH_H = 268;
export const GRAPH_PAD = 36;

export function accountTail(id) {
  const raw = String(id || "");
  if (!raw) return "";
  if (raw === "CASH-AGG") return "现金";
  if (raw === "POS-AGG") return "POS";
  return raw.replace(/^6222-/, "");
}

export function nodeCaption(n) {
  const name = String(n.label || n.id || "").replace(/（合成）/g, "").trim();
  const tail = accountTail(n.id);
  if (n.kind === "channel") return { primary: name || tail, secondary: "" };
  if (!name || name === n.id) return { primary: tail, secondary: "" };
  if (name.length > 5 && tail && tail !== name) {
    const short = name.length > 6 ? `${name.slice(0, 6)}…` : name;
    return { primary: tail, secondary: short };
  }
  return { primary: name.length > 8 ? `${name.slice(0, 8)}…` : name, secondary: tail !== name ? tail : "" };
}

export function longestPath(ids, edges) {
  const adj = new Map(ids.map((id) => [id, []]));
  for (const e of edges) {
    if (adj.has(e.source) && adj.has(e.target)) adj.get(e.source).push(e.target);
  }
  let best = [];
  function walk(id, seen) {
    let local = [id];
    for (const nxt of adj.get(id) || []) {
      if (seen.has(nxt)) continue;
      seen.add(nxt);
      const tail = walk(nxt, seen);
      if (1 + tail.length > local.length) local = [id, ...tail];
      seen.delete(nxt);
    }
    return local;
  }
  for (const id of ids) {
    const path = walk(id, new Set([id]));
    if (path.length > best.length) best = path;
  }
  return best;
}

export function initialLayout(nodes, edges) {
  const map = {};
  if (!nodes.length) return map;
  const ids = nodes.map((n) => n.id);
  const path = longestPath(ids, edges);
  const useFlow = path.length >= 3 && path.length >= Math.min(nodes.length, 3);
  if (useFlow) {
    const placed = new Set(path);
    path.forEach((id, i) => {
      const n = nodes.find((x) => x.id === id);
      const t = path.length === 1 ? 0.5 : i / (path.length - 1);
      map[id] = {
        ...n,
        x: GRAPH_PAD + t * (GRAPH_W - GRAPH_PAD * 2),
        y: GRAPH_H * 0.46 + Math.sin(t * Math.PI) * 28 * (i % 2 === 0 ? 1 : -1),
      };
    });
    const rest = nodes.filter((n) => !placed.has(n.id));
    rest.forEach((n, i) => {
      const a = (Math.PI * 2 * i) / Math.max(rest.length, 1) - Math.PI / 2;
      map[n.id] = {
        ...n,
        x: GRAPH_W / 2 + Math.cos(a) * 78,
        y: GRAPH_H * 0.72 + Math.sin(a) * 28,
      };
    });
    return map;
  }
  const cx = GRAPH_W / 2;
  const cy = GRAPH_H * 0.46;
  const others = nodes.filter((n) => n.kind !== "center");
  nodes.forEach((n) => {
    if (n.kind === "center") map[n.id] = { ...n, x: cx, y: cy };
  });
  const r = others.length > 6 ? 72 : 88;
  others.forEach((n, i) => {
    const a = (Math.PI * 2 * i) / Math.max(others.length, 1) - Math.PI / 2;
    map[n.id] = { ...n, x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * 70 };
  });
  nodes.forEach((n) => {
    if (!map[n.id]) map[n.id] = { ...n, x: cx, y: cy };
  });
  return map;
}
