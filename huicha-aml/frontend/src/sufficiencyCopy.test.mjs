import { sufficiencyHeadline } from "./sufficiencyCopy.js";

if (sufficiencyHeadline({ verified: true, necessary_ids: [] }) !== "已在候选预算内收敛") {
  throw new Error("verified headline");
}
if (sufficiencyHeadline({ verified: false, necessary_ids: ["TX-1"] }) !== "已找到必要证据，但未宣称全局最小") {
  throw new Error("necessary but unverified headline");
}
if (sufficiencyHeadline({ verified: false, necessary_ids: [] }) !== "预算耗尽，未形成稳定核心") {
  throw new Error("unstable core headline");
}

console.log("sufficiency copy ok");
