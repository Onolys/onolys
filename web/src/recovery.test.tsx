import { useEffect } from "react";
import { act, render, screen, fireEvent } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, recoveryDetails } from "./api/errors";
import { ErrorBoundary } from "./ErrorBoundary";
import { ErrorRecovery } from "@onolys/common";
import { RouteError } from "./routes/RouteError";
import { routes } from "./routes/routes";
import { mockEmitter, server } from "./mocks/server";
import { createMemoryStatusEmitter, setStatusListener } from "./api/statusListener";
import { renderApp } from "./test/renderApp";

const USER = { email: "rater@clinic.org", verified: true };
afterEach(() => { vi.restoreAllMocks(); setStatusListener(mockEmitter); });

describe("page recovery", () => {
  it("offers reload and back, showing only a safe status and reference", () => {
    const reload = vi.fn();
    render(<ErrorRecovery {...recoveryDetails(new ApiError(503, "private transcript", [], "req-123.example"))} reload={reload} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.getByText("Error 503")).toBeInTheDocument();
    expect(screen.getByText("Reference: req-123.example")).toBeInTheDocument();
    expect(screen.queryByText(/private transcript/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Reload page" }));
    expect(reload).toHaveBeenCalledOnce();
    expect(screen.getByRole("link", { name: "Back to the start" })).toHaveAttribute("href", "/");
  });

  it("never displays raw exception or untrusted reference text", () => {
    render(<ErrorRecovery {...recoveryDetails(new ApiError(500, "internal_error", [], "patient@example.org"))} />);
    expect(screen.queryByText(/patient@example/)).toBeNull();
  });

  it("recovers a failure outside the router, including the auth provider", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    function Crash(): never { throw new Error("private startup details"); }
    render(<ErrorBoundary><Crash /></ErrorBoundary>);
    expect(screen.getByRole("main")).toHaveTextContent("Something went wrong");
    expect(screen.queryByText(/private startup/)).toBeNull();
  });

  it("recovers provider initialization effects outside the router", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    function ProviderCrash() {
      useEffect(() => { throw new Error("private auth details"); }, []);
      return <div>Starting</div>;
    }
    render(<ErrorBoundary><ProviderCrash /></ErrorBoundary>);
    expect(screen.getByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.queryByText(/private auth/)).toBeNull();
  });

  it("recovers a layout crash through the root route boundary", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    function Crash(): never { throw new Error("private layout details"); }
    await renderApp("/sessions", { user: USER, routes: [{ ...routes[0], element: <Crash /> }] });
    expect(await screen.findByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it.each([400, 404, 503])("keeps HTTP %s meaningful without exposing response data", async (status) => {
    const router = createMemoryRouter([{
      path: "/", element: <div>page</div>, errorElement: <RouteError />,
      loader: () => { throw new Response("private response details", { status }); },
    }]);
    render(<RouterProvider router={router} />);
    expect(await screen.findByRole("heading", { name: status === 404 ? "Page not found" : "Something went wrong" })).toBeInTheDocument();
    expect(screen.getByText(`Error ${status}`)).toBeInTheDocument();
    expect(screen.queryByText(/private response/)).toBeNull();
  });

  it.each([503, "network"] as const)("recovers an initial sessions %s failure", async (status) => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    server.use(http.get("*/v1/sessions", () => status === "network"
      ? HttpResponse.error()
      : HttpResponse.json({ request_id: "req-503", details: [{ code: "internal_error", message: "private server details" }] }, { status })));
    await renderApp("/sessions", { user: USER });
    expect(await screen.findByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload page" })).toBeInTheDocument();
    expect(screen.queryByText(/private server/)).toBeNull();
  });

  it("recovers an initial session status failure when live updates and API are unavailable", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    setStatusListener(createMemoryStatusEmitter({ reportMissing: true }));
    server.use(http.get("*/v1/sessions/:id", () => HttpResponse.json({}, { status: 503 })));
    await renderApp("/sessions/s1", { user: USER });
    expect(await screen.findByRole("heading", { name: "Something went wrong" }, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText("Error 503")).toBeInTheDocument();
  });

  it("keeps usable sessions on a failed background refresh", async () => {
    let fail = false;
    server.use(http.get("*/v1/sessions", () => fail
      ? HttpResponse.json({}, { status: 503 })
      : HttpResponse.json({ items: [{ id: "s1", title: "Saved session", status: "running", created_at: "2026-11-24T10:00:00Z", latest_report_version: null, error_code: null }] })));
    const { queryClient } = await renderApp("/sessions", { user: USER });
    expect(await screen.findByRole("link", { name: "Saved session" })).toBeInTheDocument();
    fail = true;
    await act(async () => { await queryClient.refetchQueries({ queryKey: ["sessions"] }); });
    expect(screen.getByRole("link", { name: "Saved session" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reload page" })).toBeNull();
  });

  it("recovers an essential report read without replacing report not-found behavior", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    server.use(http.get("*/v1/sessions/:id/reports/:version", () => HttpResponse.json({}, { status: 502 })));
    await renderApp("/sessions/s1/reports/1", { user: USER });
    expect(await screen.findByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.getByText("Error 502")).toBeInTheDocument();
  });

  it("keeps a normal 400 query failure local", async () => {
    server.use(http.get("*/v1/sessions", () => HttpResponse.json({ details: [{ code: "invalid_parameters", message: "bad input" }] }, { status: 400 })));
    await renderApp("/sessions", { user: USER });
    expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Sessions" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reload page" })).toBeNull();
  });
});
