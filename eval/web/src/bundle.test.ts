/** One copy of the shared libraries: prod auth sources (web/src) must resolve them from eval/web/node_modules. */
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build, type Rollup } from "vite";
import { expect, it } from "vitest";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SHARED = ["react", "react-dom", "react-router", "firebase", "@tanstack/react-query", "openapi-fetch", "@onolys/ui"];

it("bundles exactly one copy of react, firebase and the other shared packages, all from eval/web", async () => {
  const out = (await build({ root, logLevel: "silent", build: { write: false } })) as Rollup.RollupOutput | Rollup.RollupOutput[];
  const modules = (Array.isArray(out) ? out : [out]).flatMap((o) => o.output).flatMap((c) => (c.type === "chunk" ? Object.keys(c.modules) : []));
  const roots = new Map<string, Set<string>>();
  for (const id of modules) {
    const m = /^(.*\/node_modules\/((?:@[^/]+\/)?[^/]+))\//.exec(id.replace(/\0/g, ""));
    if (m) roots.set(m[2], (roots.get(m[2]) ?? new Set()).add(m[1]));
  }
  for (const pkg of SHARED) {
    const copies = [...(roots.get(pkg) ?? [])];
    expect(copies, pkg).toHaveLength(1);
    expect(copies[0], pkg).toBe(resolve(root, "node_modules", pkg));
  }
  // Prod auth is bundled (not a stub) and nothing was pulled from web/node_modules.
  expect(modules.some((id) => id.includes("/web/src/auth/AuthProvider"))).toBe(true);
  expect(modules.filter((id) => id.startsWith(resolve(root, "../../web/node_modules")))).toEqual([]);
}, 120_000);
