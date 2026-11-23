import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { server } from "../../mocks/server";
import { renderApp } from "../../test/renderApp";

afterEach(() => {
  server.events.removeAllListeners();
  window.location.hash = "";
  vi.unstubAllEnvs();
});

describe("/sample", () => {
  it("renders the new view with zero network requests, signed out", async () => {
    const requests: string[] = [];
    server.events.on("request:start", ({ request }) => void requests.push(`${request.method} ${request.url}`));
    renderApp("/sample");
    const main = within(screen.getByRole("main"));
    expect(await main.findByRole("heading", { level: 1, name: "Sample report" })).toBeInTheDocument();
    expect(main.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "At a glance",
      "Feedback: ideas to try",
      "Behaviour counts",
      "Coded transcript",
      "Method & limits",
    ]);
    expect(main.getByRole("button", { name: "Open coded transcript" })).toBeEnabled();
    await new Promise((r) => setTimeout(r, 50));
    expect(requests).toEqual([]);
  });

  it("shows the grey example line and no yellow Sample banner", async () => {
    renderApp("/sample");
    const main = within(screen.getByRole("main"));
    expect(await main.findByText("Example report from a made-up role-play conversation.")).toBeInTheDocument();
    expect(main.queryByText(/^Sample$/)).toBeNull();
    expect(main.queryByRole("note")).toBeNull();
    expect(document.querySelector(".notice")).toBeNull();
  });

  it("opens the coded transcript with the closing pleasantry marked Not coded", async () => {
    renderApp("/sample");
    const main = within(screen.getByRole("main"));
    await userEvent.click(await main.findByRole("button", { name: "Open coded transcript" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getAllByText("Not coded").length).toBeGreaterThan(0);
  });

  it("has no Run again, rating, delete or version controls", async () => {
    renderApp("/sample");
    const main = within(screen.getByRole("main"));
    await main.findByRole("heading", { name: "At a glance" });
    expect(main.queryByRole("button", { name: /run again|rating|delete/i })).toBeNull();
    expect(main.queryByLabelText("Version")).toBeNull();
  });
});
