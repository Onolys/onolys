import { describe, expect, it } from "vitest";
import { FAKE_UID, fakeToken, fakeTokenProvider } from "./fake";

describe("fake auth", () => {
  it("uses the API fake bearer format `test:<uid>`", async () => {
    expect(fakeToken("abc")).toBe("test:abc");
    expect(await fakeTokenProvider()()).toBe(`test:${FAKE_UID}`);
    expect(await fakeTokenProvider("zed")(true)).toBe("test:zed");
  });
});
