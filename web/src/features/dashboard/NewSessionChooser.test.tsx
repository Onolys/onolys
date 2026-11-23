import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { mockBackend } from "../../mocks/server";
import { here } from "../../test/renderApp";
import { renderPage } from "../../test/renderPage";
import { NewSessionChooser } from "./NewSessionChooser";

const USER = { email: "rater@clinic.org", verified: true };
const render = () => renderPage(<NewSessionChooser />, "/new", { user: USER });
const main = () => within(screen.getByRole("main"));

describe("new session chooser", () => {
  it("has the New Session h1, no Sessions heading, and both cards", async () => {
    render();
    expect(await screen.findByRole("heading", { level: 1, name: "New Session" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "Sessions" })).toBeNull();
    expect(main().getByRole("heading", { level: 2, name: "Practise with an AI client" })).toBeInTheDocument();
    expect(main().getByRole("heading", { level: 2, name: "Rate a recording" })).toBeInTheDocument();
    expect(main().getByRole("link", { name: "Start AI Interview" })).toHaveAttribute("href", "/interviews/new");
  });

  it("shows the usage lines and a New session link", async () => {
    const { router } = render();
    expect(await main().findByText("20 of 20 left today")).toBeInTheDocument();
    expect(main().getByText("5 of 5 left today")).toBeInTheDocument();
    const meters = main().getAllByRole("meter");
    expect(meters).toHaveLength(2);
    expect(meters[0]).toHaveAttribute("aria-valuetext", "5 of 5 left today");
    expect(meters[1]).toHaveAttribute("aria-valuetext", "20 of 20 left today");
    const link = main().getByRole("link", { name: "New session" });
    expect(link).toHaveAttribute("href", "/sessions/new");
    await userEvent.click(link);
    expect(here(router)).toBe("/sessions/new");
  });

  it("over the eval cap: says so with the reset time", async () => {
    mockBackend.configure({ caps: { eval: { day: 0 } } });
    render();
    expect(await main().findByText("0 of 0 left today")).toBeInTheDocument();
    expect(main().getByText(/reached today's limit/i)).toHaveTextContent(/after .+/);
  });

  it("over the interview cap: disables Start AI Interview and explains", async () => {
    mockBackend.configure({ caps: { interview: { day: 0 } } });
    const { router } = render();
    const btn = await main().findByRole("button", { name: "Start AI Interview" });
    expect(btn).toBeDisabled();
    expect(main().queryByRole("link", { name: "Start AI Interview" })).toBeNull();
    expect(main().getByText(/limit|reached/i)).toBeInTheDocument();
    expect(here(router)).toBe("/new");
  });
});
