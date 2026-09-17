import { collectSignBlockers, reliabilityStance, signBlockerText } from "./signBlockers.js";

const abstainInv = {
  use_challenger: true,
  can_sign: false,
  sign_blockers: [{ code: "cf_invalid", message: "反事实轮次输出无效，不能判断证据依赖" }],
  agent_reliability: { stance: "abstain", reasons: [{ code: "cf_invalid", message: "反事实轮次输出无效，不能判断证据依赖" }] },
  judge_validation: { passed: true },
};
const factInv = {
  use_challenger: true,
  can_sign: false,
  fact_issues: [{ token: "6222-FAKE-9999" }],
  sign_blockers: [{ code: "fact_check", message: "事实回查未通过" }],
};
if (signBlockerText(abstainInv).includes("反事实") === false) {
  throw new Error("abstain blocker text missing");
}
if (collectSignBlockers(factInv)[0].message !== "事实回查未通过") {
  throw new Error("fact check blocker should stay explicit");
}
if (reliabilityStance(abstainInv) !== "abstain" || reliabilityStance({ use_challenger: false }) !== "committed") {
  throw new Error("reliability stance mapping failed");
}

console.log("sign blockers ok");
