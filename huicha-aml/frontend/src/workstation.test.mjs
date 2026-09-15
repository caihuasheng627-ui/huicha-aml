import { isDoneStatus, isTodoStatus } from "./workstation.js";

const investigator = { role: "反洗钱调查员" };
const reviewer = { role: "合规复核" };

if (!isTodoStatus("pending", investigator) || !isTodoStatus("investigating", investigator)) {
  throw new Error("investigator todo should include pending/investigating");
}
if (isTodoStatus("pending_review", investigator)) {
  throw new Error("investigator todo must not keep pending_review after submit");
}
if (!isDoneStatus("pending_review", investigator)) {
  throw new Error("investigator done should include submitted pending_review");
}
if (!isTodoStatus("pending_review", reviewer) || isTodoStatus("pending", reviewer)) {
  throw new Error("reviewer todo should be pending_review only");
}
if (isDoneStatus("pending_review", reviewer) || !isDoneStatus("ready_to_file", reviewer)) {
  throw new Error("reviewer done is after签发, not while waiting to review");
}

console.log("workstation queue ok");
