import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { afterEach, describe, expect, it } from "vitest";

const html = readFileSync("index.html", "utf8");
afterEach(() => document.body.replaceChildren());

describe("static startup recovery", () => {
  it("provides native recovery links before any JS or stylesheet loads", () => {
    document.body.innerHTML = html.match(/<body>([\s\S]*)<\/body>/)![1];
    const recovery = document.getElementById("startup-recovery")!;
    expect(recovery).not.toBeNull();
    expect(recovery.querySelector('a[href=""]')).toHaveTextContent("Reload page");
    expect(recovery.querySelector('a[href="/"]')).toHaveTextContent("Back to the start");
    expect(html).not.toMatch(/\son\w+\s*=/);
    expect(html).not.toMatch(/<style|\sstyle=/);
    expect(html.match(/<script[^>]*>[^<]+<\/script>/)).toBeNull();
  });
  it.each(["error", "unhandledrejection", "vite:preloadError"])("shows safe recovery on an early %s", (event) => {
    document.body.innerHTML = html.match(/<body>([\s\S]*)<\/body>/)![1];
    const listeners: Record<string, () => void> = {};
    const isolatedWindow = { addEventListener: (name: string, cb: () => void) => { listeners[name] = cb; } };
    runInNewContext(readFileSync("public/boot-recovery.js", "utf8"), { window: isolatedWindow, document });
    listeners[event]();
    expect(document.querySelector('[role="alert"]')).toHaveTextContent("Something went wrong");
    expect(document.activeElement?.tagName).toBe("H1");
    // A late event cannot replace a running React app.
    document.getElementById("root")!.textContent = "Running app";
    listeners[event]();
    expect(document.getElementById("root")).toHaveTextContent("Running app");
  });
});
