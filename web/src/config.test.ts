import { afterEach, describe, expect, it, vi } from "vitest";
import { ratingEnabled } from "./config";

afterEach(() => vi.unstubAllEnvs());

describe("ratingEnabled", () => {
  it("is off when VITE_RATING_ENABLED is absent or empty", () => {
    vi.stubEnv("VITE_RATING_ENABLED", "");
    expect(ratingEnabled()).toBe(false);
  });

  it.each(["false", "1", "TRUE", "yes"])("is off for %j", (v) => {
    vi.stubEnv("VITE_RATING_ENABLED", v);
    expect(ratingEnabled()).toBe(false);
  });

  it("is on only for the exact string true, re-read on every call", () => {
    vi.stubEnv("VITE_RATING_ENABLED", "true");
    expect(ratingEnabled()).toBe(true);
    vi.stubEnv("VITE_RATING_ENABLED", "false");
    expect(ratingEnabled()).toBe(false);
  });
});
