import { shouldFallbackInvestigate } from "./api.js";

const connectFail = new Error("无法连接调查服务");
connectFail.streamFailed = true;
if (!shouldFallbackInvestigate(connectFail)) {
  throw new Error("stream not opened should fallback to POST");
}

const timeoutAfterOpen = new Error("调查超时");
if (shouldFallbackInvestigate(timeoutAfterOpen)) {
  throw new Error("opened stream timeout must not fallback to POST");
}

const incomplete = new Error("调查流未完成");
if (shouldFallbackInvestigate(incomplete)) {
  throw new Error("opened stream incomplete must not fallback to POST");
}

const conflict = new Error("本案正在调查");
if (shouldFallbackInvestigate(conflict)) {
  throw new Error("409 must not fallback to POST");
}

console.log("investigate fallback ok");
