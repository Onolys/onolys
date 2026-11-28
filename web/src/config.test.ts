import { afterEach, describe, expect, it, vi } from "vitest";
import { appHosts, ratingEnabled } from "./config";

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

describe("appHosts", () => {
  it("is the auth domain plus the configured VITE_APP_HOSTS, trimmed and lowercased", () => {
    expect(appHosts({ VITE_APP_HOSTS: " Staging.Example , other.example", VITE_FIREBASE_AUTH_DOMAIN: "auth.example" })).toEqual([
      "auth.example",
      "staging.example",
      "other.example",
    ]);
  });

  it("falls back to the default app hosts when VITE_APP_HOSTS is unset or empty", () => {
    for (const v of [undefined, "", " , "]) {
      const hosts = appHosts({ VITE_APP_HOSTS: v, VITE_FIREBASE_AUTH_DOMAIN: "auth.example" });
      expect(new Set(hosts)).toEqual(new Set(["auth.example", "app.onolys.com", "onolys-app.web.app", "onolys-staging-app.web.app"]));
      expect(hosts).not.toContain("onolys-app-staging.web.app");
    }
    expect(appHosts({ VITE_APP_HOSTS: "x.example" })).not.toContain("app.onolys.com");
  });
});
