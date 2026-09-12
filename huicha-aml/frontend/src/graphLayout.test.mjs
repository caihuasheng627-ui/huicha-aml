import { initialLayout, longestPath, nodeCaption } from "./graphLayout.js";

const nodes = [
  { id: "6222-L-A", label: "过桥账户演示（合成）", kind: "counterparty" },
  { id: "6222-L-B", label: "过桥账户演示（合成）", kind: "center" },
  { id: "6222-L-C", label: "过桥账户演示（合成）", kind: "counterparty" },
  { id: "6222-L-D", label: "过桥账户演示（合成）", kind: "counterparty" },
];
const edges = [
  { source: "6222-L-A", target: "6222-L-B" },
  { source: "6222-L-B", target: "6222-L-C" },
  { source: "6222-L-C", target: "6222-L-D" },
];

const path = longestPath(nodes.map((n) => n.id), edges);
if (path.join(">") !== "6222-L-A>6222-L-B>6222-L-C>6222-L-D") {
  throw new Error(`unexpected path ${path.join(">")}`);
}

const layout = initialLayout(nodes, edges);
const xs = ["6222-L-A", "6222-L-B", "6222-L-C", "6222-L-D"].map((id) => layout[id].x);
if (!(xs[0] < xs[1] && xs[1] < xs[2] && xs[2] < xs[3])) {
  throw new Error(`flow layout is not left-to-right: ${xs}`);
}

const cap = nodeCaption(nodes[0]);
if (cap.primary !== "L-A") throw new Error(`expected L-A, got ${cap.primary}`);
if (!cap.secondary.includes("过桥")) throw new Error(`expected 过桥 subtitle, got ${cap.secondary}`);

console.log("graphLayout ok");
