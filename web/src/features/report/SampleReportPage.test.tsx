import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { server } from "../../mocks/server";
import { renderApp } from "../../test/renderApp";

afterEach(() => {
  server.events.removeAllListeners();
  window.location.hash = "";
  vi.unstubAllEnvs();
});

describe("/sample-report", () => {
  it("renders the bundled report and transcript with zero network requests, signed out", async () => {
    const requests: string[] = [];
    server.events.on("request:start", ({ request }) => void requests.push(`${request.method} ${request.url}`));
    renderApp("/sample-report");
    const main = within(screen.getByRole("main"));
    expect(await main.findByRole("heading", { name: "Sample report" })).toBeInTheDocument();
    expect(main.getByText(/^Sample$/)).toBeInTheDocument();
    expect(main.getByRole("region", { name: "Scorecard" })).toBeInTheDocument();
    expect(main.getByRole("region", { name: "Transcript" })).toHaveTextContent("I'd like to start walking more");
    await new Promise((r) => setTimeout(r, 50));
    expect(requests).toEqual([]);
  });

  it("has no Run again, rating or delete controls", async () => {
    renderApp("/sample-report");
    const main = within(screen.getByRole("main"));
    await main.findByRole("region", { name: "Scorecard" });
    expect(main.queryByRole("button", { name: /run again/i })).toBeNull();
    expect(main.queryByRole("button", { name: /rating/i })).toBeNull();
    expect(main.queryByRole("button", { name: /delete/i })).toBeNull();
  });

  it("shows the no-rating sample (Item + Onolys only) with the flag off", async () => {
    renderApp("/sample-report");
    const main = within(screen.getByRole("main"));
    const score = within(await main.findByRole("region", { name: "Scorecard" }));
    expect(score.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Item", "Onolys"]);
    expect(main.queryByRole("region", { name: "Disagreements" })).toBeNull();
  });

  it("uses the no-rating fixture with the flag on too (PRD R5: unconditional): no Disagreements or reasons", async () => {
    vi.stubEnv("VITE_RATING_ENABLED", "true");
    renderApp("/sample-report");
    const main = within(screen.getByRole("main"));
    await main.findByRole("region", { name: "Scorecard" });
    expect(main.queryByRole("region", { name: "Disagreements" })).toBeNull();
    expect(main.queryByRole("region", { name: "Your reasons, checked" })).toBeNull();
  });
});
