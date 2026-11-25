import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { createFakeAuthService } from "../auth/fakeService";
import { registerJob, getJob } from "../features/upload/uploader";
import type { UploadJob } from "../features/upload/uploader";
import { here, renderApp } from "../test/renderApp";

const crash = vi.hoisted(() => ({ on: false }));
vi.mock("../features/dashboard/SessionsPage", () => ({
  SessionsPage: () => {
    if (crash.on) throw new Error("boom");
    return <h1>Sessions</h1>;
  },
}));

const h1 = (name: string) => screen.findByRole("heading", { level: 1, name });
const navNames = () =>
  within(screen.getByRole("navigation", { name: "Main" }))
    .queryAllByRole("link")
    .map((a) => a.textContent);
const inNav = () => within(screen.getByRole("navigation", { name: "Main" }));
/** A plain nav link: an <a> with no Button styling (no data-slot/data-variant, no border/background/pill classes). */
function expectPlainLink(a: HTMLElement) {
  expect(a.tagName).toBe("A");
  expect(a).not.toHaveAttribute("data-slot");
  expect(a).not.toHaveAttribute("data-variant");
  expect(a).not.toHaveAttribute("data-size");
  expect(a.className).not.toMatch(/(^|\s)(border|bg-|rounded|shadow|px-)/);
}

describe("header nav by auth phase (D1)", () => {
  it("signed out: plain Log in and Sign up links at the far right, no Sample report", async () => {
    renderApp("/login");
    await h1("Log in");
    expect(navNames()).toEqual(["Log in", "Sign up"]);
    const login = inNav().getByRole("link", { name: "Log in" });
    const signup = inNav().getByRole("link", { name: "Sign up" });
    expect(login).toHaveAttribute("href", "/login");
    expect(signup).toHaveAttribute("href", "/signup");
    for (const a of [login, signup]) expectPlainLink(a);
    expect(login).toHaveAttribute("aria-current", "page");
    expect(signup).not.toHaveAttribute("aria-current");
    expect(inNav().queryByRole("link", { name: "Sample report" })).not.toBeInTheDocument();
    expect(login.nextElementSibling).toBe(signup);
    expect(signup.nextElementSibling).toBeNull();
    expect(inNav().queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
  });

  it("verified: the current page's nav link has aria-current", async () => {
    renderApp("/new", { user: { email: "a@clinic.org", verified: true } });
    await h1("Welcome a");
    expect(inNav().getByRole("link", { name: "New Session" })).toHaveAttribute("aria-current", "page");
    expect(inNav().getByRole("link", { name: "Sessions" })).not.toHaveAttribute("aria-current");
  });

  it("unverified: header is the brand only (not a signed-in state)", async () => {
    renderApp("/verify-email", { user: { email: "a@clinic.org", verified: false } });
    await h1("Verify your email");
    const header = within(screen.getByRole("banner"));
    expect(header.getAllByRole("link").map((a) => a.textContent)).toEqual(["Onolys"]);
    expect(header.queryByRole("button")).not.toBeInTheDocument();
    expect(header.queryByText("a@clinic.org")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 }).closest("section")).toHaveAttribute("data-page", "verify-email");
  });

  it("verified: Sessions and New Session plain links, no Sample report; email and Sign out live in the account menu", async () => {
    renderApp("/sessions", { user: { email: "a@clinic.org", verified: true } });
    await h1("Sessions");
    expect(navNames()).toEqual(["New Session", "Sessions"]);
    for (const n of ["Sessions", "New Session"]) expectPlainLink(inNav().getByRole("link", { name: n }));
    expect(inNav().getByRole("link", { name: "Sessions" })).toHaveAttribute("href", "/sessions");
    expect(inNav().getByRole("link", { name: "New Session" })).toHaveAttribute("href", "/new");
    expect(inNav().queryByRole("link", { name: "Sample report" })).not.toBeInTheDocument();
    expect(inNav().queryByText("a@clinic.org")).not.toBeInTheDocument();
    expect(inNav().queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Account menu" })).toHaveTextContent("A");
  });

  it("verified: page nav is centred in the header (true centre)", async () => {
    renderApp("/sessions", { user: { email: "a@clinic.org", verified: true } });
    await h1("Sessions");
    const nav = screen.getByRole("navigation", { name: "Main" });
    const header = nav.parentElement!;
    expect(header).toHaveClass("relative", "[&>nav]:absolute", "[&>nav]:left-1/2", "[&>nav]:-translate-x-1/2");
  });

  it("signed out: nav is not centred (stays right)", async () => {
    renderApp("/login");
    await h1("Log in");
    expect(screen.getByRole("banner")).not.toHaveClass("[&>nav]:absolute");
  });

  it("account menu: opens with email, Settings and Sign out; closes on Escape, outside click and selection", async () => {
    renderApp("/sessions", { user: { email: "a@clinic.org", verified: true } });
    await h1("Sessions");
    const btn = screen.getByRole("button", { name: "Account menu" });
    expect(btn).toHaveAttribute("aria-haspopup", "menu");
    expect(btn).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "true");
    const menu = within(screen.getByRole("menu"));
    expect(menu.getByText("a@clinic.org")).toBeInTheDocument();
    expect(menu.getByRole("menuitem", { name: "Settings" })).toHaveAttribute("href", "/settings");
    expect(menu.getByRole("menuitem", { name: "Sign out" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
    expect(btn).toHaveFocus();
    await userEvent.click(btn);
    await userEvent.click(screen.getByRole("heading", { level: 1 }));
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
    await userEvent.click(btn);
    await userEvent.click(btn);
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
  });

  it("account menu keyboard: open focuses first item; arrows, Home/End cycle; Escape returns focus; Tab closes", async () => {
    renderApp("/sessions", { user: { email: "a@clinic.org", verified: true } });
    await h1("Sessions");
    const btn = screen.getByRole("button", { name: "Account menu" });
    await userEvent.click(btn);
    const settings = screen.getByRole("menuitem", { name: "Settings" });
    const signOut = screen.getByRole("menuitem", { name: "Sign out" });
    // Opening uses requestAnimationFrame; Radix arrow navigation defers focus to a task.
    await waitFor(() => expect(settings).toHaveFocus());
    await userEvent.keyboard("{ArrowDown}");
    await waitFor(() => expect(signOut).toHaveFocus());
    await userEvent.keyboard("{ArrowDown}");
    await waitFor(() => expect(settings).toHaveFocus());
    await userEvent.keyboard("{ArrowUp}");
    await waitFor(() => expect(signOut).toHaveFocus());
    await userEvent.keyboard("{Home}");
    await waitFor(() => expect(settings).toHaveFocus());
    await userEvent.keyboard("{End}");
    await waitFor(() => expect(signOut).toHaveFocus());
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
    await waitFor(() => expect(btn).toHaveFocus());
    await userEvent.click(btn);
    expect(screen.getByRole("menu")).toBeInTheDocument();
    await userEvent.tab();
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
  });

  it("account menu: Settings navigates and closes", async () => {
    const { router } = renderApp("/sessions", { user: { email: "a@clinic.org", verified: true } });
    await h1("Sessions");
    await userEvent.click(screen.getByRole("button", { name: "Account menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Settings" }));
    await h1("Settings");
    expect(here(router)).toBe("/settings");
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
  });

  it("account menu: choosing Settings leaves focus on the Settings heading, not the trigger", async () => {
    renderApp("/sessions", { user: { email: "a@clinic.org", verified: true } });
    await h1("Sessions");
    await userEvent.click(screen.getByRole("button", { name: "Account menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Settings" }));
    const heading = await h1("Settings");
    await new Promise((r) => setTimeout(r, 100)); // let Radix's deferred close auto-focus run
    expect(heading).toHaveFocus();
    expect(screen.getByRole("button", { name: "Account menu" })).not.toHaveFocus();
  });

  it("account menu: Sign out calls the service sign-out and lands on /login", async () => {
    const service = createFakeAuthService();
    const spy = vi.spyOn(service, "signOut");
    const { router } = renderApp("/sessions", { service, user: { email: "a@clinic.org", verified: true } });
    await h1("Sessions");
    await userEvent.click(screen.getByRole("button", { name: "Account menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    await h1("Log in");
    expect(spy).toHaveBeenCalledTimes(1);
    expect(here(router)).toBe("/login");
  });

  it("loading: brand only", async () => {
    const service = createFakeAuthService();
    service.onAuthStateChanged = () => () => {};
    renderApp("/settings", { service });
    await screen.findByRole("status");
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Onolys" })).toBeInTheDocument();
  });

  it("header Sign out lands on plain /login", async () => {
    const { router } = renderApp("/settings", { user: { email: "a@clinic.org", verified: true } });
    await h1("Settings");
    await userEvent.click(screen.getByRole("button", { name: "Account menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    await h1("Log in");
    expect(here(router)).toBe("/login");
  });

  it("a failing sign-out shows an error, stays signed in and keeps the cache", async () => {
    const service = createFakeAuthService();
    vi.spyOn(service, "signOut").mockRejectedValue(new Error("network"));
    const { router, queryClient } = renderApp("/settings", { service, user: { email: "a@clinic.org", verified: true } });
    queryClient.setQueryData(["secret"], 1);
    await h1("Settings");
    await userEvent.click(screen.getByRole("button", { name: "Account menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't sign out/i);
    expect(here(router)).toBe("/settings");
    expect(queryClient.getQueryData(["secret"])).toBe(1);
  });
});

describe("404 by phase", () => {
  it("verified: Back to your sessions goes to /sessions", async () => {
    const { router } = renderApp("/nope", { user: { email: "a@clinic.org", verified: true } });
    await h1("Page not found");
    await userEvent.click(await within(screen.getByRole("main")).findByRole("link", { name: "Back to your sessions" }));
    await h1("Sessions");
    expect(here(router)).toBe("/sessions");
  });

  it.each([
    [undefined, "Log in"],
    [{ email: "a@clinic.org", verified: false }, "Verify your email"],
    [{ email: "a@clinic.org", verified: true }, "Back to your sessions"],
  ] as const)("%j offers %s", async (user, link) => {
    renderApp("/nope", user ? { user } : {});
    await h1("Page not found");
    const main = within(screen.getByRole("main"));
    expect(await main.findByRole("link", { name: link })).toBeInTheDocument();
    expect(main.getAllByRole("link")).toHaveLength(1);
  });
});

describe("user change", () => {
  it("clears the query cache and upload registry when the uid changes or the user signs out elsewhere", async () => {
    const service = createFakeAuthService();
    const { queryClient } = renderApp("/settings", { service, user: { email: "a@clinic.org", verified: true } });
    await h1("Settings");
    const cancel = vi.fn();
    registerJob("s1", { cancel, active: true } as unknown as UploadJob);
    queryClient.setQueryData(["secret"], 1);
    service.signedInAs("b@clinic.org", { verified: true });
    await waitFor(() => expect(queryClient.getQueryData(["secret"])).toBeUndefined());
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(getJob("s1")).toBeUndefined();
  });

  it("keeps the cache when the same user is re-reported", async () => {
    const service = createFakeAuthService();
    const { queryClient } = renderApp("/settings", { service, user: { email: "a@clinic.org", verified: true } });
    await h1("Settings");
    queryClient.setQueryData(["keep"], 1);
    service.signedInAs("a@clinic.org", { verified: true });
    await h1("Settings");
    expect(queryClient.getQueryData(["keep"])).toBe(1);
  });
});

describe("root error element", () => {
  it("a render crash keeps the header and a way back", async () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    crash.on = true;
    renderApp("/sessions", { user: { email: "a@clinic.org", verified: true } });
    await h1("Something went wrong");
    expect(screen.getByRole("link", { name: "Onolys" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the start" })).toBeInTheDocument();
    err.mockRestore();
    crash.on = false;
  });
});
