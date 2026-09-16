import { parseSseBlocks } from "./api.js";

const sample = [
  "event: stage",
  "data: {\"role\":\"Judge\",\"status\":\"started\"}",
  "",
  "event: stage",
  "data: {\"role\":\"Judge\",\"status\":\"finished\",\"elapsed_ms\":12}",
  "",
  "event: done",
  "data: {\"payload\":{\"conclusion\":\"exclude\"}}",
  "",
].join("\n");

const { events, rest } = parseSseBlocks(`${sample}\n`);
if (rest !== "") throw new Error(`complete SSE should leave empty rest, got ${JSON.stringify(rest)}`);
if (events.length !== 3) throw new Error(`expected 3 events, got ${events.length}`);
if (events[0].event !== "stage" || events[0].data.role !== "Judge") {
  throw new Error("first event should be Judge started");
}
if (events[2].event !== "done" || events[2].data.payload.conclusion !== "exclude") {
  throw new Error("done payload should parse");
}

const partial = parseSseBlocks("event: stage\ndata: {\"role\":\"Planner\"");
if (partial.events.length !== 0) throw new Error("incomplete block must stay in rest");
if (!partial.rest.includes("Planner")) throw new Error("incomplete block should be retained");

console.log("sse parse ok");
