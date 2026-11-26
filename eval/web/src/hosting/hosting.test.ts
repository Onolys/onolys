/** `eval/web/firebase.json` CSP must let the Firebase auth iframe load from the configured authDomain (D5). */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getConfig } from "../config";

interface Entry { headers?: { source: string; headers: { key: string; value: string }[] }[] }
const cfg = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../firebase.json"), "utf8")) as { hosting: Entry | Entry[] };
const entries = Array.isArray(cfg.hosting) ? cfg.hosting : [cfg.hosting];

function csp(entry: Entry): Record<string, string[]> {
  const value = entry.headers?.find((h) => h.source === "**")?.headers.find((h) => h.key === "Content-Security-Policy")?.value;
  if (!value) throw new Error("no Content-Security-Policy header");
  const out: Record<string, string[]> = {};
  for (const part of value.split(";")) {
    const [name, ...sources] = part.trim().split(/\s+/);
    if (name) out[name] = sources;
  }
  return out;
}

afterEach(() => vi.unstubAllEnvs());

describe("eval/web/firebase.json", () => {
  it("frame-src allows the default Firebase authDomain host (*.firebaseapp.com) and Google sign-in", () => {
    vi.stubEnv("VITE_FIREBASE_AUTH_DOMAIN", "");
    const authDomain = getConfig().firebase.authDomain;
    expect(authDomain).toBe("onolys-eval.firebaseapp.com");
    expect(authDomain.endsWith(".firebaseapp.com")).toBe(true); // covered by the wildcard frame-src below
    for (const entry of entries) {
      expect(csp(entry)["frame-src"]).toEqual(expect.arrayContaining(["https://*.firebaseapp.com", "https://accounts.google.com"]));
    }
  });
});

it("connect-src permits the signed GCS upload host", () => {
  for (const entry of entries) expect(csp(entry)["connect-src"]).toContain("https://storage.googleapis.com");
});
