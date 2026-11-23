/** Small development stand-in for the authoritative API transcript parsers. */
import type { Schemas } from "../api/types";
import { MockHttpError } from "./stateMachine";

export function mockTranscriptUpload(raw: string, media: string): Schemas["TranscriptView"] {
  const fail = (code: string, status = 422): never => { throw new MockHttpError(status, code, "Check the transcript."); };
  if (new TextEncoder().encode(raw).length > 1024 * 1024) fail("transcript_too_large", 413);
  if (!raw.trim()) fail("empty_transcript");
  let transcript: Schemas["TranscriptView"];
  if (media === "application/json") {
    try { transcript = JSON.parse(raw) as Schemas["TranscriptView"]; }
    catch { return fail("transcript_invalid"); }
  } else if (media === "text/plain") {
    const turns: Schemas["TranscriptView"]["turns"] = [];
    for (const line of raw.replace(/^\uFEFF/, "").replace(/\r\n/g, "\n").split("\n")) {
      if (!line.trim()) continue;
      const match = /^([^:]{1,40}):\s*(.*)$/.exec(line);
      if (match) {
        const label = match[1];
        const speaker = /^[tc]$/i.test(label) ? label.toUpperCase() : label;
        turns.push({ id: `t${turns.length + 1}`, speaker, role: speaker === "T" ? "clinician" : speaker === "C" ? "client" : null, text: match[2] });
      } else if (turns.length) turns[turns.length - 1].text += `\n${line}`;
      else fail("transcript_invalid");
    }
    transcript = { turns, language: "en" };
  } else return fail("unsupported_media_type", 415);
  if (!transcript || !Array.isArray(transcript.turns) || transcript.turns.some((t) => !t || typeof t.text !== "string" || !t.text.trim() || typeof t.speaker !== "string" || !t.speaker)) fail("transcript_invalid");
  if (new Set(transcript.turns.filter((t) => t.role === "clinician").map((t) => t.speaker)).size > 1) fail("transcript_invalid");
  if (transcript.turns.map((t) => t.text).join(" ").trim().split(/\s+/).length < 50) fail("empty_transcript");
  return transcript;
}
