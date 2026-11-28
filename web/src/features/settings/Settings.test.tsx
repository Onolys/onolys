import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderApp } from "../../test/renderApp";
import { server } from "../../mocks/server";

const USER = { email: "rater@clinic.org", verified: true };
const main = () => within(screen.getByRole("main"));

describe("settings: usage failure (I2)", () => {
  it("shows an error with Retry, not 'Loading…' forever, then recovers", async () => {
    const user = userEvent.setup();
    let fail = true;
    server.use(
      http.get("*/v1/usage", ({ request }) => {
        if (!fail) return undefined;
        void request;
        return HttpResponse.json(
          { schema_version: "0.0.1", error: { code: "internal_error", message: "boom", request_id: "req_u", details: [] } },
          { status: 500 },
        );
      }),
    );
    await renderApp("/settings", { user: USER });
    const retry = await main().findByRole("button", { name: "Retry" }, { timeout: 4000 });
    expect(main().queryByText("Loading…")).toBeNull();
    fail = false;
    await user.click(retry);
    expect(await main().findByText(/Ratings:/)).toBeInTheDocument();
    expect(main().queryByRole("button", { name: "Retry" })).toBeNull();
  });
});

describe("settings", () => {
  it("shows usage and account-removal information without API tools or sign out", async () => {
    const apiKeyCalls: string[] = [];
    server.use(http.all("*/v1/api-key", ({ request }) => {
      apiKeyCalls.push(request.method);
      return HttpResponse.json({ active: false });
    }));
    const { queryClient } = await renderApp("/settings", { user: USER });
    expect(await main().findByText("20 of 20 left today")).toBeInTheDocument();
    expect(main().getByText("5 of 5 left today")).toBeInTheDocument();
    expect(main().getByText(/account removal/i)).toBeInTheDocument();
    expect(main().getByRole("link", { name: "tejitpabari99@gmail.com" })).toHaveAttribute("href", "mailto:tejitpabari99@gmail.com");
    expect(main().getByText(/deleting a session removes/i)).toBeInTheDocument();
    expect(main().queryAllByText(/api key|use the api|curl|api docs/i)).toHaveLength(0);
    expect(main().queryByRole("button", { name: "Sign out" })).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(apiKeyCalls).toEqual([]);
    expect(queryClient.getQueryCache().find({ queryKey: ["api-key"] })).toBeUndefined();
  });

  it("keeps sign out in the avatar menu and clears the query cache", async () => {
    const user = userEvent.setup();
    const { router, queryClient } = await renderApp("/settings", { user: USER });
    await main().findByText("20 of 20 left today");
    expect(queryClient.getQueryCache().getAll().length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Account menu" }));
    await user.click(screen.getByRole("menuitem", { name: "Sign out" }));
    await waitFor(() => expect(router.state.location.pathname + router.state.location.search).toBe("/login"));
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });
});
