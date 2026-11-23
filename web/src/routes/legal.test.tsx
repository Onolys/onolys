import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderApp } from "../test/renderApp";

const h1 = (name: string) => screen.findByRole("heading", { level: 1, name });

describe("legal pages", () => {
  it.each([
    ["/privacy", "Privacy Policy"],
    ["/terms", "Terms of Service"],
  ])("%s renders signed out with an updated date", async (path, heading) => {
    renderApp(path);
    await h1(heading);
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
    expect(within(main).getByText(/no other user can access/i)).toBeInTheDocument();
    expect(within(main).getByText(/full control over your data/i)).toBeInTheDocument();
    expect(within(main).getByText(/delete your data at any time/i)).toBeInTheDocument();
  });
});

describe("privacy accuracy", () => {
  it("covers interview audio, API keys and what deletion keeps", async () => {
    renderApp("/privacy");
    await h1("Privacy Policy");
    const main = within(screen.getByRole("main"));
    expect(main.getByText(/practice-interview audio/i)).toBeInTheDocument();
    expect(main.getByText(/api key/i)).toBeInTheDocument();
    expect(main.getByText(/are kept\. To remove/i)).toBeInTheDocument();
  });
});

describe("footer", () => {
  it.each([[undefined], [{ email: "a@clinic.org", verified: true }]])("shows legal links and copyright (%o)", async (user) => {
    renderApp("/sample-report", user ? { user } : {});
    await screen.findByRole("heading", { level: 1, name: "Sample report" });
    const footer = screen.getByRole("contentinfo");
    expect(within(footer).getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/privacy");
    expect(within(footer).getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
    const contact = within(footer).getByRole("link", { name: "Contact" });
    expect(contact).toHaveAttribute("href", expect.stringMatching(/^mailto:/));
    expect(within(footer).getAllByRole("link")).toHaveLength(3);
    expect(within(footer).getByText(`© ${new Date().getFullYear()} Onolys`)).toBeInTheDocument();
    expect(within(footer).getByText("Not official MITI coding")).toBeInTheDocument();
    expect(within(footer).getByText("Use it to practice and prepare")).toBeInTheDocument();
    expect(within(footer).getByText("Role-play or de-identified transcripts only")).toBeInTheDocument();
    expect(footer).not.toHaveTextContent("Questions?");
    expect(footer).not.toHaveTextContent("All rights reserved");
    expect(footer.querySelectorAll("[style]")).toHaveLength(0);
  });
});
