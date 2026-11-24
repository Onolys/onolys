// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createAuthSession } from "./auth";
import { createFakeProvider } from "./auth/fakeProvider";
import { Root } from "./Root";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("VITE_ADMIN_API_URL", "https://api.example.test");
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

const json = (status: number, body: unknown = {}) => new Response(JSON.stringify(body), { status });
const signedIn = () => createAuthSession(createFakeProvider({ email: "admin@example.com" }));

describe("Shell", () => {
  it("200 from /v1/me: shows email, Sign out and the empty page", async () => {
    fetchMock.mockResolvedValue(json(200, { status: "ok" }));
    render(<Root session={signedIn()} />);
    expect(await screen.findByText("Nothing here yet.")).toBeTruthy();
    expect(screen.getByText("admin@example.com")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.example.test/v1/me");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok-0");
  });

  it("403 from /v1/me: shows Not allowed, not the empty page", async () => {
    fetchMock.mockResolvedValue(json(403, { detail: "forbidden" }));
    render(<Root session={signedIn()} />);
    expect(await screen.findByText("Not allowed")).toBeTruthy();
    expect(screen.queryByText("Nothing here yet.")).toBeNull();
  });

  it("gate off (no session): renders the empty page and makes no fetch", () => {
    render(<Root session={null} />);
    expect(screen.getByText("Nothing here yet.")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("network error: shows a retry message, then recovers on Retry", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch")).mockResolvedValue(json(200, { status: "ok" }));
    render(<Root session={signedIn()} />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("Nothing here yet.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByText("Nothing here yet.")).toBeTruthy());
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("5xx from /v1/me: shows a retry message, not the empty page, then recovers on Retry", async () => {
    fetchMock.mockResolvedValueOnce(json(503, { detail: "unavailable" })).mockResolvedValue(json(200, { status: "ok" }));
    render(<Root session={signedIn()} />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("Nothing here yet.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByText("Nothing here yet.")).toBeTruthy());
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("200 HTML from /v1/me (SPA rewrite): not the empty page, shows an unexpected-response retry", async () => {
    fetchMock.mockResolvedValue(new Response("<!doctype html><html></html>", { status: 200, headers: { "content-type": "text/html" } }));
    render(<Root session={signedIn()} />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText(/unexpected response/i)).toBeTruthy();
    expect(screen.queryByText("Nothing here yet.")).toBeNull();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("404 from /v1/me: not the empty page", async () => {
    fetchMock.mockResolvedValue(json(404, { detail: "Not Found" }));
    render(<Root session={signedIn()} />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("Nothing here yet.")).toBeNull();
  });

  it("429 from /v1/me: says to wait, not the empty page, and Retry recovers", async () => {
    fetchMock.mockResolvedValueOnce(json(429, { detail: "slow down" })).mockResolvedValue(json(200, { status: "ok" }));
    render(<Root session={signedIn()} />);
    expect(await screen.findByText(/too many requests/i)).toBeTruthy();
    expect(screen.queryByText("Nothing here yet.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByText("Nothing here yet.")).toBeTruthy());
  });

  it("auth required but VITE_ADMIN_API_URL unset: config error, no request", async () => {
    vi.stubEnv("VITE_ADMIN_API_URL", "");
    render(<Root session={signedIn()} />);
    expect(await screen.findByText(/VITE_ADMIN_API_URL/)).toBeTruthy();
    expect(screen.queryByText("Nothing here yet.")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
