import { describe, expect, it } from "vitest";
import { testEmail, uidForEmail } from "./renderApp";

/** Vitest runs test files in parallel against one auth emulator: two files must never share an account. */
describe("test accounts are isolated per test file", () => {
  const inFile = (path: string, run: () => void) => {
    const previous = expect.getState().testPath;
    expect.setState({ testPath: path });
    try {
      run();
    } finally {
      expect.setState({ testPath: previous });
    }
  };

  it("derives a different email and uid for the same logical user in different files", () => {
    let a = { email: "", uid: "" };
    let b = { email: "", uid: "" };
    inFile("/repo/web/src/a.test.tsx", () => (a = { email: testEmail("rater@clinic.org"), uid: uidForEmail("rater@clinic.org") }));
    inFile("/repo/web/src/b.test.tsx", () => (b = { email: testEmail("rater@clinic.org"), uid: uidForEmail("rater@clinic.org") }));
    expect(a.email).not.toBe(b.email);
    expect(a.uid).not.toBe(b.uid);
  });

  it("is stable within one file, and different logical users stay different", () => {
    expect(testEmail("rater@clinic.org")).toBe(testEmail("rater@clinic.org"));
    expect(testEmail("a@clinic.org")).not.toBe(testEmail("b@clinic.org"));
  });

  it("keeps the local part and domain readable, and the uid follows the account email", () => {
    expect(testEmail("rater@clinic.org")).toMatch(/^rater@[a-z0-9]+\.clinic\.org$/);
    expect(uidForEmail("rater@clinic.org")).toBe(`u_${testEmail("rater@clinic.org").replace(/[^a-z0-9]+/g, "_")}`);
  });
});
