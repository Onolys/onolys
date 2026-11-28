/** Design rule 1: no horizontal scroll anywhere. Scans every CSS file and inline style under src for overflow-x: auto|scroll (allowlist is empty). */
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";

const src = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SCROLL_X = /overflow-x\s*:\s*(auto|scroll)\b/i;
/** Shorthand `overflow: auto|scroll` (either value), not overflow-x/-y. */
const SCROLL_SHORT = /(?<![-\w])overflow\s*:\s*(auto|scroll)\b|(?<![-\w])overflow\s*:\s*\w+\s+(auto|scroll)\b/i;
const TW_SCROLL_X = /(?<![-\w])overflow-x-(auto|scroll)\b/;
const INLINE_SCROLL_X = /overflowX\s*:\s*['"`](auto|scroll)['"`]/;

/** Returns "line: text" for each offending line in a source string. */
export function findHorizontalScroll(source: string): string[] {
  return source.split("\n").flatMap((line, i) => (SCROLL_X.test(line) || SCROLL_SHORT.test(line) || TW_SCROLL_X.test(line) || INLINE_SCROLL_X.test(line) ? [`${i + 1}: ${line.trim()}`] : []));
}

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = join(dir, e.name);
    return e.isDirectory() ? walk(p) : [p];
  });
}

it("detects overflow-x auto/scroll in css and inline styles (seeded fixtures)", () => {
  expect(findHorizontalScroll(".a { overflow-x: auto; }")).toHaveLength(1);
  expect(findHorizontalScroll(".a{overflow-x:scroll}")).toHaveLength(1);
  expect(findHorizontalScroll("<div style={{ overflowX: 'auto' }} />")).toHaveLength(1);
  expect(findHorizontalScroll(".a { overflow: auto; }")).toHaveLength(1);
  expect(findHorizontalScroll(".a{overflow:scroll}")).toHaveLength(1);
  expect(findHorizontalScroll(".a { overflow: hidden auto; }")).toHaveLength(1);
  expect(findHorizontalScroll('<div className="overflow-x-auto p-2" />')).toHaveLength(1);
  expect(findHorizontalScroll(".a { overflow-y: auto; overflow-x: hidden; }")).toHaveLength(0);
  expect(findHorizontalScroll(".a { overflow: hidden; } .b { overflow-y: scroll; }")).toHaveLength(0);
});

it("no css or inline style under the eval UI sources scrolls horizontally", () => {
  const hits = walk(src)
    .filter((f) => /\.(css|tsx?)$/.test(f) && !f.endsWith("overflowGuard.test.ts"))
    .flatMap((f) => findHorizontalScroll(readFileSync(f, "utf8")).map((h) => `${f.slice(src.length + 1)}:${h}`));
  expect(hits).toEqual([]);
});
