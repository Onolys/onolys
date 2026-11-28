/** Property tests (review 2026-11-21) for api/errors and src/lib. See auth.property.test.ts header. */
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import {
  ApiError,
  ERROR_CODES,
  GENERIC_MESSAGE,
  describeError,
  failureView,
  messageForCode,
  parseErrorBody,
} from "../api/errors";
import {
  buildIndexMap,
  codePointLength,
  sliceCodePoints,
} from "../lib/codepoints";
import { formatElapsed, formatResetTime } from "../lib/format";
import { buildSegments } from "../lib/spans";

describe("api/errors", () => {
  it("unknown codes (incl. prototype keys) map to the generic message", () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.string(),
          fc.constantFrom(
            "__proto__",
            "constructor",
            "toString",
            "hasOwnProperty",
            "valueOf",
          ),
        ),
        (c) => {
          fc.pre(!(ERROR_CODES as string[]).includes(c));
          expect(messageForCode(c)).toBe(GENERIC_MESSAGE);
        },
      ),
    );
  });

  it("messages never echo the resetsAt context for non-cap codes", () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...ERROR_CODES),
        fc.string({ minLength: 3 }),
        (code, at) => {
          const m = messageForCode(code, { resetsAt: at });
          if (code !== "daily_cap_reached")
            expect(m).not.toContain(at);
        },
      ),
    );
  });

  it("parseErrorBody never throws and keeps status for any body", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 100, max: 599 }),
        fc.anything(),
        (status, body) => {
          const e = parseErrorBody(status, body);
          expect(e).toBeInstanceOf(ApiError);
          expect(e.status).toBe(status);
          expect(typeof e.code).toBe("string");
          expect(e.userMessage.length).toBeGreaterThan(0);
        },
      ),
    );
  });

  it("parseErrorBody takes the first well-formed detail code; 429 without details is rate_limited", () => {
    fc.assert(
      fc.property(fc.string({ minLength: 1 }), (code) => {
        const e = parseErrorBody(500, {
          details: [{ code, message: "m" }],
          request_id: "r",
        });
        expect(e.code).toBe(code);
        expect(e.requestId).toBe("r");
      }),
    );
    expect(parseErrorBody(429, {}).code).toBe("rate_limited");
  });

  it("describeError never leaks server text", () => {
    fc.assert(
      fc.property(fc.string({ minLength: 4 }), (text) => {
        fc.pre(!GENERIC_MESSAGE.includes(text));
        const d = describeError(
          parseErrorBody(500, {
            message: text,
            details: [{ code: "x", message: text }],
          }),
        );
        expect(d.message).not.toContain(text);
      }),
    );
  });


  it("failureView is total and always yields a message and a known action", () => {
    fc.assert(
      fc.property(
        fc.option(fc.string(), { nil: undefined }),
        fc.option(fc.string(), { nil: undefined }),
        fc.option(fc.integer({ min: 0, max: 5 }), { nil: undefined }),
        (code, kind, left) => {
          const v = failureView({ error_code: code ?? null, error_kind: kind as never, retries_left: left });
          expect(["retry", "new_session", "upload_different"]).toContain(v.action);
          expect(v.message.length).toBeGreaterThan(0);
        },
      ),
    );
  });
});

describe("lib/format", () => {
  it("formatElapsed is m:ss for finite input", () => {
    fc.assert(
      fc.property(fc.double({ noNaN: true, min: -1e9, max: 1e12 }), (ms) => {
        expect(formatElapsed(ms)).toMatch(/^\d+:\d\d$/);
      }),
    );
  });

  // F6 (fixed): NaN / Infinity used to render as "NaN:NaN" / "Infinity:NaN".
  it("F6: formatElapsed(NaN | Infinity) still renders m:ss", () => {
    fc.assert(
      fc.property(fc.constantFrom(NaN, Infinity, -Infinity), (ms) => {
        expect(formatElapsed(ms)).toMatch(/^\d+:\d\d$/);
      }),
    );
  });

  it("formatResetTime never throws and is undefined for unparseable input", () => {
    fc.assert(
      fc.property(fc.option(fc.string(), { nil: undefined }), (s) => {
        const r = formatResetTime(s);
        if (r !== undefined)
          expect(Number.isNaN(new Date(s as string).getTime())).toBe(false);
      }),
    );
  });
});

const anyText = fc.string({ unit: "binary" }); // includes lone surrogates

describe("lib/codepoints", () => {
  it("length equals Array.from length; map is monotone and ends at text.length", () => {
    fc.assert(
      fc.property(anyText, (t) => {
        expect(codePointLength(t)).toBe(Array.from(t).length);
        const m = buildIndexMap(t);
        expect(m.length).toBe(codePointLength(t) + 1);
        expect(m[m.length - 1]).toBe(t.length);
        for (let i = 1; i < m.length; i++)
          expect(m[i]).toBeGreaterThan(m[i - 1]);
      }),
    );
  });

  it("sliceCodePoints matches Array.from slicing for in-range offsets", () => {
    fc.assert(
      fc.property(anyText, fc.nat(40), fc.nat(40), (t, a, b) => {
        const n = codePointLength(t);
        const s = Math.min(a, n);
        const e = Math.min(Math.max(b, s), n);
        expect(sliceCodePoints(t, s, e)).toBe(
          Array.from(t).slice(s, e).join(""),
        );
      }),
    );
  });

  // F7 (fixed): out-of-range / negative offsets used to fall back to the whole tail/head instead of "".
  it(
    "F7: sliceCodePoints with negative or reversed offsets returns empty",
    () => {
      expect(sliceCodePoints("abc", -1, 2)).toBe("");
      expect(sliceCodePoints("abc", 2, 1)).toBe("");
    },
  );
});

describe("lib/spans buildSegments", () => {
  const spanFor = (t: string) =>
    fc
      .array(
        fc.record({
          id: fc.string({ minLength: 1, maxLength: 4 }),
          start: fc.integer({ min: -2, max: 30 }),
          end: fc.integer({ min: -2, max: 30 }),
        }),
        { maxLength: 6 },
      )
      .map((xs) =>
        xs.map((s) => ({ ...s, quote: sliceSafe(t, s.start, s.end) })),
      );
  const sliceSafe = (t: string, a: number, b: number) =>
    a >= 0 && b >= a && b <= codePointLength(t)
      ? sliceCodePoints(t, a, b)
      : "x";

  it("segments always concatenate back to the text; no empty segments for non-empty text", () => {
    fc.assert(
      fc.property(
        anyText.chain((t) => fc.tuple(fc.constant(t), spanFor(t))),
        ([t, spans]) => {
          const { segments } = buildSegments(t, spans);
          expect(segments.map((s) => s.text).join("")).toBe(t);
          if (t.length > 0)
            for (const s of segments) expect(s.text.length).toBeGreaterThan(0);
        },
      ),
    );
  });

  it("every span is either rejected or covered by segments listing its id", () => {
    fc.assert(
      fc.property(
        anyText.chain((t) => fc.tuple(fc.constant(t), spanFor(t))),
        ([t, spans]) => {
          const { segments, rejected } = buildSegments(t, spans);
          const used = new Set(segments.flatMap((s) => s.ids));
          for (const sp of spans) {
            if (rejected.includes(sp)) continue;
            expect(used.has(sp.id)).toBe(true);
          }
        },
      ),
    );
  });

  it("rejects exactly the spans whose range or quote is invalid", () => {
    fc.assert(
      fc.property(
        anyText,
        fc.integer({ min: -3, max: 40 }),
        fc.integer({ min: -3, max: 40 }),
        (t, s, e) => {
          const n = codePointLength(t);
          const valid = Number.isInteger(s) && s >= 0 && s < e && e <= n;
          const { rejected } = buildSegments(t, [
            {
              id: "a",
              start: s,
              end: e,
              quote: valid ? sliceCodePoints(t, s, e) : "x",
            },
          ]);
          expect(rejected.length).toBe(valid ? 0 : 1);
        },
      ),
    );
  });
});
