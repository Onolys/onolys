import { cleanup, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderApp } from "../test/renderApp";

const VERIFIED = { email: "a@clinic.org", verified: true };

const table: Array<[string, string]> = [
  ["/sample", "Sample report"],
  ["/new", "New Session"],
  ["/sessions", "Sessions"],
  ["/sessions/new", "New session"],
  ["/sessions/abc123", "Session"],
  ["/sessions/abc123/reports/2", "Report"],
  ["/settings", "Settings"],
];

const authPages: Array<[string, string]> = [
  ["/signup", "Sign up"],
  ["/login", "Log in"],
  ["/forgot-password", "Reset your password"],
];

describe("route table", () => {
  it.each(table)("%s renders its placeholder h1 for a verified user", async (path, heading) => {
    renderApp(path, { user: VERIFIED });
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
  });

  it.each(authPages)("%s renders its h1 when signed out", async (path, heading) => {
    renderApp(path);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
  });

  it("/verify-email renders for a signed-in unverified user", async () => {
    renderApp("/verify-email", { user: { email: "a@clinic.org", verified: false } });
    expect(await screen.findByRole("heading", { level: 1, name: "Verify your email" })).toBeInTheDocument();
  });

  it("/auth/action renders signed out, signed-in unverified and signed-in verified without redirect", async () => {
    const path = "/auth/action?mode=verifyEmail&oobCode=abc";
    for (const user of [undefined, { email: "a@clinic.org", verified: false }, VERIFIED]) {
      const { router } = renderApp(path, user ? { user } : {});
      // A verified user's page swaps to "Already verified" once auth state loads; accept either, and don't hold the element across the swap.
      await screen.findByRole("heading", { level: 1, name: /^(Verify your email|Already verified)$/ });
      expect(router.state.location.pathname).toBe("/auth/action");
      cleanup();
    }
  });

  it("has banner, nav, main and contentinfo landmarks", async () => {
    renderApp("/sessions", { user: VERIFIED });
    await screen.findByRole("heading", { level: 1, name: "Sessions" });
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Footer" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });

  it("/ redirects a verified user to /new", async () => {
    const { router } = renderApp("/", { user: VERIFIED });
    expect(await screen.findByRole("heading", { level: 1, name: "New Session" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/new");
  });

  it("shows a not-found page for unknown paths", async () => {
    renderApp("/nope/nothing");
    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
  });
});
