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
  it("has the Welcome h1, no Sessions heading, and both cards", async () => {
    render();
    expect(await screen.findByRole("heading", { level: 1, name: "Welcome rater" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "Sessions" })).toBeNull();
    expect(main().getByRole("heading", { level: 2, name: "Practise with an AI client" })).toBeInTheDocument();
    expect(main().getByRole("heading", { level: 2, name: "Rate a recording" })).toBeInTheDocument();
    expect(main().getByRole("link", { name: "Start AI Interview" })).toHaveAttribute("href", "/interviews/new");
  });

  it("greets by Firebase displayName (trimmed) when set", async () => {
    renderPage(<NewSessionChooser />, "/new", { user: { ...USER, displayName: "  Dana Lee " } });
    expect(await screen.findByRole("heading", { level: 1, name: "Welcome Dana Lee" })).toBeInTheDocument();
  });

  it("falls back to the email local part when displayName is blank", async () => {
    renderPage(<NewSessionChooser />, "/new", { user: { ...USER, displayName: "   " } });
    expect(await screen.findByRole("heading", { level: 1, name: "Welcome rater" })).toBeInTheDocument();
  });

  it("is just Welcome when there is neither name nor email", async () => {
    renderPage(<NewSessionChooser />, "/new", { user: { ...USER, email: "" } });
    expect(await screen.findByRole("heading", { level: 1, name: "Welcome" })).toBeInTheDocument();
  });

  it("shows the usage lines and a New session link", async () => {
    const { router } = render();
    expect(await main().findByRole("button", { name: "20 of 20 left today" })).toHaveTextContent("20/20");
    expect(main().getByRole("button", { name: "5 of 5 left today" })).toHaveTextContent("5/5");
    expect(main().queryAllByRole("meter")).toHaveLength(0);
    const link = main().getByRole("link", { name: "New session" });
    expect(link).toHaveAttribute("href", "/sessions/new");
    await userEvent.click(link);
    expect(here(router)).toBe("/sessions/new");
  });

  it("over the eval cap: says so with the reset time", async () => {
    mockBackend.configure({ caps: { eval: { day: 0 } } });
    render();
    const count = await main().findByRole("button", { name: "0 of 0 left today" });
    expect(count).toHaveTextContent("0/0");
    expect(count.querySelector(".text-destructive")).not.toBeNull();
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
