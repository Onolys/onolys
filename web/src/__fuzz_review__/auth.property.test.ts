/**
 * Property tests from the full-app review (docs/agent_files/review-full-app-20261121).
 * They assert CORRECT behaviour; known bugs use `it.fails` tagged with the finding id (F#/W#) so
 * they flip to a failure once fixed (then change `it.fails` to `it`).
 */
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { errorCode, mapAuthError } from "../auth/errors";
import { loginUrl, readNext, verifyUrl, withNext } from "../auth/next";

const ORIGIN = "https://app.example";
const sameOrigin = (target: string) =>
  new URL(target, ORIGIN).origin === ORIGIN;
const q = (next: string) => `?next=${encodeURIComponent(next)}`;

describe("readNext", () => {
  it("always returns a rooted path that is not protocol-relative", () => {
    fc.assert(
      fc.property(fc.string(), (next) => {
        const r = readNext(q(next));
        expect(r.startsWith("/")).toBe(true);
        expect(r.startsWith("//")).toBe(false);
        expect(r.includes("\\")).toBe(false);
      }),
    );
  });

  it("never throws on arbitrary search strings", () => {
    fc.assert(fc.property(fc.string(), (s) => typeof readNext(s) === "string"));
  });

  it("returns plain same-site paths unchanged", () => {
    fc.assert(
      fc.property(fc.stringMatching(/^\/[a-z0-9/_-]{0,30}$/), (p) => {
        fc.pre(!p.startsWith("//"));
        expect(readNext(q(p))).toBe(p);
      }),
    );
  });

  // F5: browsers strip ASCII tab/newline/CR from URLs, so "/\t/evil.com" resolves to //evil.com.
  it.fails(
    "F5: result resolves to the app origin for any input (no open redirect)",
    () => {
      fc.assert(
        fc.property(
          fc.string({
            unit: fc.constantFrom(
              "/",
              "\t",
              "\n",
              "\r",
              "\\",
              ".",
              "a",
              "%",
              ":",
            ),
          }),
          (next) => {
            expect(sameOrigin(readNext(q(next)))).toBe(true);
          },
        ),
        { numRuns: 500, examples: [["/\t/evil.com"]] },
      );
    },
  );
});

describe("loginUrl / verifyUrl / withNext round trip", () => {
  const path = fc
    .stringMatching(/^\/[a-z0-9/_-]{0,20}$/)
    .filter((p) => !p.startsWith("//"));
  const search = fc.oneof(
    fc.constant(""),
    fc.stringMatching(/^\?[a-z]=[a-z0-9]{0,6}$/),
  );

  it("loginUrl carries pathname+search through readNext", () => {
    fc.assert(
      fc.property(path, search, (p, s) => {
        fc.pre(p + s !== "/");
        const url = loginUrl(p, s);
        expect(readNext(url.slice(url.indexOf("?")))).toBe(p + s);
      }),
    );
  });

  it("verifyUrl carries pathname+search through readNext", () => {
    fc.assert(
      fc.property(path, search, (p, s) => {
        fc.pre(p + s !== "/");
        const url = verifyUrl(p, s);
        expect(readNext(url.slice(url.indexOf("?")))).toBe(p + s);
      }),
    );
  });

  it("withNext never emits an unvalidated next", () => {
    fc.assert(
      fc.property(fc.string(), (next) => {
        const out = withNext("/login", q(next));
        const n = readNext(
          out.includes("?") ? out.slice(out.indexOf("?")) : "",
        );
        expect(n.startsWith("//")).toBe(false);
        expect(n.startsWith("/")).toBe(true);
      }),
    );
  });
});

describe("mapAuthError / errorCode", () => {
  it("returns a non-empty fixed message for any code, including prototype keys", () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.string(),
          fc.constantFrom(
            "__proto__",
            "constructor",
            "toString",
            "hasOwnProperty",
          ),
          fc.constant(undefined),
        ),
        (c) => {
          const m = mapAuthError(c);
          expect(m.message.length).toBeGreaterThan(0);
          // no raw provider text: a message never echoes the (arbitrary) code
          if (c && c.length > 3 && !c.startsWith("auth/"))
            expect(m.message).not.toContain(c);
        },
      ),
    );
  });

  it("offerLogin only for email-already-in-use", () => {
    fc.assert(
      fc.property(fc.string(), (c) => {
        expect(mapAuthError(c).offerLogin === true).toBe(
          c === "auth/email-already-in-use",
        );
      }),
    );
  });

  it("errorCode never throws and only returns strings", () => {
    fc.assert(
      fc.property(fc.anything(), (e) => {
        const c = errorCode(e);
        expect(c === undefined || typeof c === "string").toBe(true);
      }),
    );
  });
});
