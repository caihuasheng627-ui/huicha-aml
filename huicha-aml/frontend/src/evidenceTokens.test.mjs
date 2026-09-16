import { isEvidenceToken, splitEvidenceParts } from "./evidenceTokens.js";

const parts = splitEvidenceParts("资金链见 TX-L-01 与 EV-12，对照 KB-AML-1");
const tokens = parts.filter(isEvidenceToken);
if (!tokens.includes("TX-L-01") || !tokens.includes("EV-12") || !tokens.includes("KB-AML-1")) {
  throw new Error(`expected clickable tokens, got ${JSON.stringify(tokens)}`);
}
if (isEvidenceToken("资金链见") || isEvidenceToken("")) {
  throw new Error("plain text must not be treated as a token");
}

const ids = splitEvidenceParts("TX-A-01、EV-AB-9").filter(isEvidenceToken);
if (ids.join(",") !== "TX-A-01,EV-AB-9") {
  throw new Error(`evidence_ids should tokenize like report, got ${ids.join(",")}`);
}

console.log("evidence tokens ok");
