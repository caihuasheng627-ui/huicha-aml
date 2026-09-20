import { blockedSignNoteHint, checklistNoteText, collectSignBlockers, noteTemplateFor, reliabilityStance, signBlockerText, workingNoteText } from "./signBlockers.js";

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
if (!blockedSignNoteHint(abstainInv).includes("写入草稿备注") || blockedSignNoteHint({ can_sign: true })) {
  throw new Error("blocked sign should prompt writing a draft note");
}
if (!noteTemplateFor(factInv).includes("事实回查未通过") || noteTemplateFor({ can_sign: true })) {
  throw new Error("blocked fact-check should offer a note template");
}
if (!noteTemplateFor(abstainInv).includes("证据充分性") ) {
  throw new Error("cf_invalid should offer sufficiency template");
}
if (workingNoteText("判断维持观察\n\n【补证清单】用途证明") !== "判断维持观察") {
  throw new Error("working note should drop checklist block");
}
if (checklistNoteText("判断维持观察\n\n【补证清单】用途证明") !== "【补证清单】用途证明") {
  throw new Error("checklist note should keep the appended block");
}
if (checklistNoteText("只有处理意见") !== "") {
  throw new Error("no checklist mark should yield empty checklist note");
}

console.log("sign blockers ok");
