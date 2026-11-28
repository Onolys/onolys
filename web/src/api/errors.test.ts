import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  ApiError,
  ERROR_CODES,
  GENERIC_MESSAGE,
  describeError,
  describeLookupError,
  isNotFoundError,
  failureView,
  cancelErrorMessage,
  messageForCode,
  parseErrorBody,
} from "./errors";

const body = (status: number, code: string, extra: object = {}) => ({
  schema_version: "0.0.1",
  status,
  message: "fixed text",
  details: [{ code, message: "fixed text" }],
  request_id: "req_123",
  ...extra,
});

describe("messageForCode", () => {
  it.each(ERROR_CODES)("has a plain, non-empty message for %s", (code) => {
    const msg = messageForCode(code);
    expect(msg.length).toBeGreaterThan(10);
    // plain text: no code names, no HTTP jargon
    expect(msg).not.toContain(code);
    expect(msg).not.toMatch(/\b(4\d\d|5\d\d)\b/);
  });

  it("uses the exact copy the spec names for the transcription codes", () => {
    expect(messageForCode("no_speech")).toBe("We couldn't hear enough speech in this recording");
    expect(messageForCode("speakers_not_separated")).toBe(
      "We couldn't tell the two speakers apart in this recording",
    );
    expect(messageForCode("transcription_failed")).toBe("Transcription didn't finish");
  });

  it("mentions the reset time for daily_cap_reached when known", () => {
    expect(messageForCode("daily_cap_reached", { resetsAt: "tomorrow 00:00" })).toContain(
      "tomorrow 00:00",
    );
    expect(messageForCode("daily_cap_reached")).toContain("today's limit");
  });

  it("has no monthly cap any more (unknown code -> generic)", () => {
    expect(ERROR_CODES).not.toContain("monthly_cap_reached");
    expect(messageForCode("monthly_cap_reached")).toBe(GENERIC_MESSAGE);
  });

  it("has the interview cap copy", () => {
    expect(messageForCode("interview_cap_reached")).toBe("You've reached your AI interview limit.");
  });

  it("concurrent_runs: tells the user to wait for the running rating", () => {
    expect(messageForCode("concurrent_runs")).toBe(
      "You already have a rating running. Wait for it to finish.",
    );
  });

  it("email_unverified: points the user at email verification", () => {
    expect(messageForCode("email_unverified")).toBe(
      "Verify your email address to continue. Open Verify email from the menu.",
    );
  });

  it("falls back to the generic message for unknown codes", () => {
    expect(messageForCode("something_new")).toBe(GENERIC_MESSAGE);
    expect(messageForCode(undefined)).toBe(GENERIC_MESSAGE);
  });
});

describe("parseErrorBody", () => {
  it.each(ERROR_CODES)("parses a public-error-response with code %s", (code) => {
    const err = parseErrorBody(422, body(422, code));
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe(code);
    expect(err.status).toBe(422);
    expect(err.requestId).toBe("req_123");
    expect(err.userMessage).toBe(messageForCode(code));
  });

  it("keeps per-field details (rating_invalid)", () => {
    const err = parseErrorBody(422, {
      ...body(422, "rating_invalid"),
      details: [
        { code: "rating_invalid", message: "globals.cct.reason exceeds 1000 characters" },
        { code: "rating_invalid", message: "notes exceeds 3000 characters" },
      ],
    });
    expect(err.details.map((d) => d.message)).toEqual([
      "globals.cct.reason exceeds 1000 characters",
      "notes exceeds 3000 characters",
    ]);
  });

  it("degrades to a generic error for a non-contract body", () => {
    const err = parseErrorBody(502, "<html>bad gateway</html>");
    expect(err.code).toBe("unknown");
    expect(err.userMessage).toBe(GENERIC_MESSAGE);
    expect(err.status).toBe(502);
  });

  it("maps a bare 429 without a code to rate_limited", () => {
    expect(parseErrorBody(429, {}).code).toBe("rate_limited");
  });
});

describe("parseErrorBody malformed entries", () => {
  it("drops detail entries without a string code and message, keeping the valid ones", () => {
    const err = parseErrorBody(500, {
      details: [
        null,
        "x",
        { code: "no_speech" },
        { message: "only message" },
        { code: 1, message: "m" },
        { code: "c", message: 2 },
        { code: "audio_too_long", message: "ok" },
      ],
    });
    expect(err.details).toEqual([{ code: "audio_too_long", message: "ok" }]);
    expect(err.code).toBe("audio_too_long");
  });

  it("ignores non-array details and a non-string request_id", () => {
    const err = parseErrorBody(500, { details: "nope", request_id: 123 });
    expect(err.details).toEqual([]);
    expect(err.requestId).toBeUndefined();
    expect(err.code).toBe("unknown");
    expect(parseErrorBody(500, { request_id: "r1" }).requestId).toBe("r1");
  });

  it("treats null and primitive bodies as contract-less", () => {
    for (const b of [null, undefined, 5, "x"]) expect(parseErrorBody(500, b).code).toBe("unknown");
  });
});

describe("known-code guards", () => {
  it("does not treat inherited object keys as known codes", () => {
    for (const c of ["toString", "constructor", "__proto__", "hasOwnProperty"]) {
      expect(messageForCode(c)).toBe(GENERIC_MESSAGE);
    }
  });

  it("new internal codes read as the generic message", () => {
    for (const c of ["output_invalid", "deadline_exceeded", "run_failed"]) {
      expect(messageForCode(c)).toBe(GENERIC_MESSAGE);
    }
  });
});

describe("describeError", () => {
  it("describes an ApiError with its reference", () => {
    const d = describeError(parseErrorBody(409, body(409, "invalid_state")));
    expect(d).toEqual({
      code: "invalid_state",
      message: messageForCode("invalid_state"),
      requestId: "req_123",
    });
  });

  it("describes any other thrown value generically", () => {
    expect(describeError(new TypeError("Failed to fetch"))).toEqual({
      code: "unknown",
      message: GENERIC_MESSAGE,
      requestId: undefined,
    });
  });
});

describe("enum parity with the public schema", () => {
  const schema = JSON.parse(
    readFileSync(
      resolve(process.cwd(), "../docs/contracts/public/public-error-response.schema.json"),
      "utf8",
    ),
  );
  const item = schema.properties.details.items.properties;

  it("every web code is in the schema enum, including the cap codes", () => {
    for (const code of ERROR_CODES) expect(item.code.enum).toContain(code);
    for (const code of ["daily_cap_reached", "interview_cap_reached", "concurrent_runs", "email_unverified"]) {
      expect(ERROR_CODES).toContain(code);
    }
  });

  it("schema period is day only", () => {
    expect(item.period.enum).toEqual(["day"]);
  });
});

describe("isNotFoundError / describeLookupError", () => {
  it("treats 404 and 422 invalid_parameters (malformed id) as not found, nothing else", () => {
    const e = (status: number, code: string) => parseErrorBody(status, body(status, code));
    expect(isNotFoundError(e(404, "not_found"))).toBe(true);
    expect(isNotFoundError(e(422, "invalid_parameters"))).toBe(true);
    expect(isNotFoundError(e(422, "rating_invalid"))).toBe(false);
    expect(isNotFoundError(e(500, "internal_error"))).toBe(false);
    expect(describeLookupError(e(422, "invalid_parameters")).code).toBe("not_found");
    expect(describeLookupError(e(500, "internal_error")).code).toBe("internal_error");
  });
});

describe("failureView", () => {
  const doc = (o: Record<string, unknown>) => ({ error_code: null, ...o }) as Parameters<typeof failureView>[0];

  it("transient with retries left: code message, not-counted note, retry action", () => {
    const v = failureView(doc({ error_code: "upstream_unavailable", error_kind: "transient", retries_left: 2, counted: false }));
    expect(v).toEqual({
      action: "retry",
      message: messageForCode("upstream_unavailable"),
      note: "This did not count toward your limit.",
    });
  });

  it("transient with no retries left: start a new session", () => {
    const v = failureView(doc({ error_code: "upstream_unavailable", error_kind: "transient", retries_left: 0 }));
    expect(v.action).toBe("new_session");
    expect(v.message).toBe("We couldn't finish this after several tries. Start a new session.");
    expect(v.note).toBeUndefined();
  });

  it("permanent_internal: our-side copy, new session, no retry", () => {
    const v = failureView(doc({ error_code: "internal_error", error_kind: "permanent_internal", retries_left: 0 }));
    expect(v.action).toBe("new_session");
    expect(v.message).toBe(
      "Something went wrong on our side. This did not count toward your limit. Please start a new session.",
    );
  });

  it("user_file: per-code text and upload action; counted sentence only when counted", () => {
    const base = { error_code: "no_speech", error_kind: "user_file", retries_left: 0 };
    const no = failureView(doc({ ...base, counted: false }));
    expect(no).toEqual({ action: "upload_different", message: messageForCode("no_speech"), note: undefined });
    const yes = failureView(doc({ ...base, counted: true }));
    expect(yes.note).toBe("This counted toward your limit.");
  });

  it("unknown code and no kind falls back to permanent_internal copy", () => {
    for (const d of [doc({ error_code: "something_new" }), doc({}), doc({ error_code: "toString" })]) {
      const v = failureView(d);
      expect(v.action).toBe("new_session");
      expect(v.message).toMatch(/on our side/);
    }
  });

  it("counted=true never adds the sentence outside user_file", () => {
    expect(failureView(doc({ error_kind: "transient", error_code: "run_failed", retries_left: 1, counted: true })).note).toBe(
      "This did not count toward your limit.",
    );
  });
});

describe("cancelErrorMessage", () => {
  it("409 reads as already finished; anything else as a retryable failure", () => {
    expect(cancelErrorMessage(parseErrorBody(409, "invalid_state"))).toBe("This session already finished or failed.");
    expect(cancelErrorMessage(parseErrorBody(500, "internal_error"))).toBe("We couldn't cancel this session. Try again.");
    expect(cancelErrorMessage(new TypeError("network"))).toBe("We couldn't cancel this session. Try again.");
  });
});

describe("session_too_long copy (C20)", () => {
  it("speaks to web users, not API users", () => {
    const msg = messageForCode("session_too_long");
    expect(msg).not.toMatch(/coded_span|API/);
    expect(msg).toMatch(/shorter/i);
  });
});
