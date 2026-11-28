import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderApp } from "../test/renderApp";

// Focus is an effect: await its observable result after a same-tab SPA navigation.
describe("route focus", () => {
  it("moves focus to the h1 on navigation", async () => {
    const { router } = await renderApp("/login");
    await waitFor(() => expect(screen.getByRole("heading", { level: 1, name: "Log in" })).toHaveFocus());
    await userEvent.click(screen.getByRole("link", { name: "Sign up" }));
    expect(router.state.location.pathname).toBe("/signup");
    await waitFor(() => expect(screen.getByRole("heading", { level: 1, name: "Sign up" })).toHaveFocus());
  });
});
