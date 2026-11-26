/** Chart deps size budget: the chart module (visx + d3 deps) built standalone, react external, gzipped, must add <= 40 KB and ship one copy of each package. */
import { dirname, resolve } from "node:path";
import { gzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { build, type Rollup } from "vite";
import { expect, it } from "vitest";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const BUDGET_BYTES = 40 * 1024;

it("added chart deps stay within 40 KB gzip and each package ships once", async () => {
  const out = (await build({
    root,
    configFile: false,
    logLevel: "silent",
    plugins: [react()],
    build: {
      write: false,
      minify: true,
      lib: { entry: resolve(root, "src/ui/chart/index.ts"), formats: ["es"], fileName: "chart" },
      rollupOptions: { external: ["react", "react-dom", "react/jsx-runtime", /^lucide-react/] },
    },
  })) as Rollup.RollupOutput | Rollup.RollupOutput[];
  const chunks = (Array.isArray(out) ? out : [out]).flatMap((o) => o.output).filter((c): c is Rollup.OutputChunk => c.type === "chunk");
  const gzip = chunks.reduce((n, c) => n + gzipSync(c.code).length, 0);
  console.info(`chart deps added: ${(gzip / 1024).toFixed(1)} KB gzip (budget 40 KB)`);
  expect(gzip).toBeGreaterThan(1024); // the chart libs really are inside the measured bundle
  expect(gzip).toBeLessThanOrEqual(BUDGET_BYTES);

  const roots = new Map<string, Set<string>>();
  for (const id of chunks.flatMap((c) => Object.keys(c.modules))) {
    const m = /^(.*\/node_modules\/((?:@[^/]+\/)?[^/]+))\//.exec(id.replace(/\0/g, ""));
    if (m) roots.set(m[2], (roots.get(m[2]) ?? new Set()).add(m[1]));
  }
  expect(roots.has("@visx/scale") && roots.has("@visx/axis") && roots.has("@visx/shape") && roots.has("@visx/group")).toBe(true);
  // One copy of every chart package. (visx/text's legacy reduce-css-calc chain bundles two balanced-match versions; tiny upstream detail, not a chart package.)
  const chartPkgs = [...roots.keys()].filter((p) => /^(@visx\/|d3-|internmap|classnames)/.test(p));
  expect(chartPkgs.length).toBeGreaterThan(4);
  for (const pkg of chartPkgs) expect([...roots.get(pkg)!], pkg).toHaveLength(1);
}, 120_000);
