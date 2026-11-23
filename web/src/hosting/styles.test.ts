/** SP2 Phase 6: only the design system styles the app. The styles folder holds just index.css and nothing references the removed bridge. */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");
const STYLES = join(SRC, "styles");
const css = readFileSync(join(STYLES, "index.css"), "utf8");

describe("styles", () => {
  it("styles folder holds only index.css", () => {
    expect(readdirSync(STYLES)).toEqual(["index.css"]);
  });

  it("index.css imports no legacy bridge or alias and names no legacy layer", () => {
    expect(css).not.toMatch(/legacy/i);
    expect(css).not.toMatch(/tokens\.css|app\.css|inter-latin/);
  });

  it("no source file imports the legacy stylesheets", () => {
    const walk = (d: string): string[] => readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(join(d, e.name)) : [join(d, e.name)]));
    for (const f of walk(SRC).filter((x) => /\.(tsx?|css)$/.test(x) && !x.endsWith("styles.test.ts"))) {
      expect(readFileSync(f, "utf8"), f).not.toMatch(/(?:import|@import)[^\n]*(?:legacy-app|legacy\.css|tokens\.css|app\.css|inter-latin)/);
    }
  });
});
