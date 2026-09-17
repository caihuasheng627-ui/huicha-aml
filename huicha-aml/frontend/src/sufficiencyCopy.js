export function sufficiencyHeadline(data) {
  if (!data) return "";
  if (data.verified) return "已在候选预算内收敛";
  if ((data.necessary_ids || []).length) return "已找到必要证据，但未宣称全局最小";
  return "预算耗尽，未形成稳定核心";
}
