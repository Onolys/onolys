import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderApp } from "../test/renderApp";

const h1 = (name: string) => screen.findByRole("heading", { level: 1, name });

describe("legal pages", () => {
  it.each([
    ["/privacy", "Privacy Policy"],
    ["/terms", "Terms of Service"],
  ])("%s renders signed out and signed in with a title", async (path, heading) => {
    renderApp(path);
    await h1(heading);
    expect(document.title).toContain(heading);
    expect(screen.getByText(/Last updated: 2026-11-23/)).toBeInTheDocument();
  });

  it.each([
    ["/privacy", "Privacy Policy"],
    ["/terms", "Terms of Service"],
  ])("%s is reachable when signed in (no redirect)", async (path, heading) => {
    renderApp(path, { user: { email: "a@clinic.org", verified: true } });
    await h1(heading);
  });

  it("privacy page states the four data-control commitments", async () => {
    renderApp("/privacy");
    await h1("Privacy Policy");
    const main = screen.getByRole("main");
    expect(within(main).getByText(/stored only for you/i)).toBeInTheDocument();
    expect(within(main).getByText(/only your own account can access/i)).toBeInTheDocument();
    expect(within(main).getByText(/full control over your data/i)).toBeInTheDocument();
    expect(within(main).getByText(/delete your data at any time/i)).toBeInTheDocument();
  });
});

describe("footer", () => {
  it.each([[undefined], [{ email: "a@clinic.org", verified: true }]])("shows legal links and copyright (%o)", async (user) => {
    renderApp("/sample-report", user ? { user } : {});
    await screen.findByRole("heading", { level: 1, name: "Sample report" });
    const footer = screen.getByRole("contentinfo");
    expect(within(footer).getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("href", "/privacy");
    expect(within(footer).getByRole("link", { name: "Terms of Service" })).toHaveAttribute("href", "/terms");
    expect(within(footer).getByRole("link", { name: "Contact" })).toHaveAttribute("href", expect.stringMatching(/^mailto:/));
    expect(within(footer).getByText(`© ${new Date().getFullYear()} Onolys. All rights reserved.`)).toBeInTheDocument();
    expect(within(footer).getByText(/Not official MITI coding/)).toBeInTheDocument();
  });
});
