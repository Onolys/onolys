import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return sources(p);
    return /\.(ts|tsx)$/.test(f) && !/\.test\.|\.d\.ts$/.test(f) ? [p] : [];
  });
}

describe("usage consumers", () => {
  it("useUsage() is the only non-test source that reads GET /usage", () => {
    const readers = sources("src").filter((p) => /GET\("\/usage"\)/.test(readFileSync(p, "utf8")));
    expect(readers).toEqual([join("src", "features", "usage", "useUsage.ts")]);
  });

  it("no source reads the removed runs_today / daily_cap fields", () => {
    const stale = sources("src").filter((p) => /runs_today|daily_cap\b/.test(readFileSync(p, "utf8")) && !p.endsWith("schema.d.ts"));
    expect(stale).toEqual([]);
  });
});
