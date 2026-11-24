/** Mobile layout needs a viewport meta (D14). */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";

it("index.html sets a device-width viewport", () => {
  const html = readFileSync(resolve(import.meta.dirname, "../../index.html"), "utf8");
  expect(html).toMatch(/<meta\s+name="viewport"\s+content="width=device-width, initial-scale=1(\.0)?"\s*\/?>/);
});
