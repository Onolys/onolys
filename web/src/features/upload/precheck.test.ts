import { describe, expect, it } from "vitest";
import { checkFile, type UploadLimits } from "./precheck";
import source from "./precheck.ts?raw";

const LIMITS: UploadLimits = {
  max_bytes: 50 * 1024 * 1024,
  max_duration_s: 30 * 60,
  interview_max_duration_s: 600,
  short_warning_s: 5 * 60,
  extensions: ["mp3", "wav", "webm"],
  mime_types: ["audio/mpeg", "audio/wav", "audio/webm"],
};
const f = (name: string, size = 1000, type = "audio/mpeg") => ({ name, size, type });
const OK = { blocked: null, warning: null };

describe("checkFile (pre-checks from served limits)", () => {
  it("has no numeric or type literals in its source", () => {
    const src = source.slice(source.indexOf("export interface UploadLimits"), source.indexOf("export const MAX_TRANSCRIPT_BYTES"));
    expect(src).not.toMatch(/300|1024 \* 1024 \* 3|20 \* 60|10 \* 60|"mp3"|"audio\/mpeg"|video\/webm/);
  });

  it("accepts a normal file inside the served limits", () => {
    expect(checkFile(f("a.mp3"), 15 * 60, LIMITS)).toEqual(OK);
  });

  it("blocks over the served size with a message built from it", () => {
    const r = checkFile(f("a.wav", LIMITS.max_bytes + 1, "audio/wav"), 900, LIMITS);
    expect(r.blocked).toBe("This file is over 50 MB. Export it as m4a or mp3 and upload that instead.");
    expect(checkFile(f("a.wav", LIMITS.max_bytes, "audio/wav"), 900, LIMITS).blocked).toBeNull();
  });

  it("accepts by served extension even when the MIME is unknown or wrong (webm as video/webm)", () => {
    expect(checkFile(f("a.WEBM", 10, "video/webm"), 900, LIMITS).blocked).toBeNull();
    expect(checkFile(f("a.mp3", 10, ""), 900, LIMITS).blocked).toBeNull();
  });

  it("accepts by served MIME when the extension is odd", () => {
    expect(checkFile(f("recording", 10, "audio/wav"), 900, LIMITS).blocked).toBeNull();
  });

  it("blocks a type that is in neither served list, naming the served extensions", () => {
    const r = checkFile(f("notes.m4a", 10, "audio/mp4"), 900, LIMITS);
    expect(r.blocked).toMatch(/mp3, wav or webm/);
  });

  it("blocks over the served max duration, in minutes from the served value", () => {
    expect(checkFile(f("a.mp3"), 30 * 60 + 1, LIMITS).blocked).toBe(
      "This recording is longer than 30 minutes. Upload a shorter one.",
    );
    expect(checkFile(f("a.mp3"), 30 * 60, LIMITS)).toEqual(OK);
  });

  it("warns (does not block) under the served short threshold", () => {
    const r = checkFile(f("a.mp3"), 5 * 60 - 1, LIMITS);
    expect(r.blocked).toBeNull();
    expect(r.warning).toMatch(/under 5 minutes/);
    expect(checkFile(f("a.mp3"), 5 * 60, LIMITS)).toEqual(OK);
  });

  it("skips every check when limits are unavailable", () => {
    const huge = f("a.pdf", 10 ** 12, "application/pdf");
    expect(checkFile(huge, 10 ** 6, undefined)).toEqual(OK);
    expect(checkFile(huge, 10 ** 6, null)).toEqual(OK);
  });

  it("skips only the duration check when the duration is unreadable", () => {
    expect(checkFile(f("a.mp3"), null, LIMITS)).toEqual(OK);
    expect(checkFile(f("a.mp3", LIMITS.max_bytes + 1), null, LIMITS).blocked).toMatch(/over 50 MB/);
  });

  it("size block wins over a duration block", () => {
    expect(checkFile(f("a.mp3", LIMITS.max_bytes + 1), 3600 * 5, LIMITS).blocked).toMatch(/over 50 MB/);
  });
});
