/** The API client's 401 handling through the app: one forced token refresh, then sign-out (the guards then send to /login). */
import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { AuthProvider, RequireVerified, type AuthService } from "@onolys/common/auth";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { server } from "../mocks/server";
import { makeQueryClient } from "../queryClient";
import { routes } from "../routes/routes";
import { here, renderApp, signInTestUser, testService } from "../test/renderApp";
import { useApiClient } from "./useApiClient";

const USER = { email: "a@clinic.org", verified: true };
const h1 = (name: string) => screen.findByRole("heading", { level: 1, name });
/** How many times the API client asked the SDK for a fresh token (`getToken(true)`). */
const forcedRefreshes = (getToken: { mock: { calls: unknown[][] } }) => getToken.mock.calls.filter(([force]) => force === true).length;

function Probe() {
  const client = useApiClient();
  const q = useQuery({
    queryKey: ["probe"],
    queryFn: async () => (await client.GET("/usage")).response.status,
    retry: false,
  });
  return <p>{q.isSuccess ? `status ${q.data}` : "pending"}</p>;
}

function ConcurrentRequests() {
  const first = useApiClient();
  const second = useApiClient();
  const [finished, setFinished] = useState(false);
  return <button onClick={() => void Promise.all([first.GET("/usage"), second.GET("/usage")]).then(() => setFinished(true))}>
    {finished ? "Requests finished" : "Request both"}
  </button>;
}

const USAGE = `${window.location.origin}/v1/usage`;

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
}

function renderWithProbe(service: AuthService, path: string) {
  const queryClient = makeQueryClient();
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider service={service}>
        <Probe />
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  );
  return { router, queryClient };
}

describe("token retry and sign-out", () => {
  it("one 401 then success: exactly one forced refresh, still signed in", async () => {
    const service = testService();
    const getToken = vi.spyOn(service, "getToken");
    await signInTestUser(service, USER);
    let n = 0;
    server.use(
      http.get(USAGE, () =>
        ++n === 1 ? new HttpResponse(null, { status: 401 }) : HttpResponse.json({ eval: { day: { used: 0, cap: 20, resets_at: "x" } }, interview: { day: { used: 0, cap: 5, resets_at: "x" } } }),
      ),
    );
    const { router } = renderWithProbe(service, "/settings");
    expect(await screen.findByText("status 200")).toBeInTheDocument();
    expect(forcedRefreshes(getToken)).toBe(1);
    await h1("Settings");
    expect(here(router)).toBe("/settings");
  });

  it("a second 401 signs out, clears the query cache and the guard sends to /login", async () => {
    let requests = 0;
    server.use(http.get(USAGE, () => {
      requests++;
      return new HttpResponse(null, { status: 401 });
    }));
    const service = testService();
    const getToken = vi.spyOn(service, "getToken");
    const signOut = vi.spyOn(service, "signOut");
    // Settings already requests usage; adding Probe here would create a second request.
    const { router, queryClient } = await renderApp("/settings", { service, user: USER });
    queryClient.setQueryData(["secret"], { phi: "x" });
    await h1("Log in");
    expect(requests).toBe(2);
    expect(forcedRefreshes(getToken)).toBe(1);
    expect(signOut).toHaveBeenCalledTimes(1);
    expect(here(router)).toBe("/login?next=%2Fsettings");
    expect(queryClient.getQueryData(["secret"])).toBeUndefined();
    expect(await service.getToken()).toBeNull();
  });

  it("concurrent requests each retry once, then sign out together and clear private data", async () => {
    let requests = 0;
    const initial = deferred();
    const retries = deferred();
    server.use(http.get(USAGE, async () => {
      const request = ++requests;
      // Keep both requests in flight, including their refreshed retries, before expiring the session.
      if (request === 2) initial.resolve();
      if (request === 4) retries.resolve();
      await (request <= 2 ? initial.promise : retries.promise);
      return new HttpResponse(null, { status: 401 });
    }));
    const service = testService();
    const getToken = vi.spyOn(service, "getToken");
    await signInTestUser(service, USER);
    const releaseSignOut = deferred();
    const originalSignOut = service.signOut;
    const signOut = vi.spyOn(service, "signOut").mockImplementation(async () => {
      await releaseSignOut.promise;
      await originalSignOut();
    });
    const { router, queryClient } = await renderApp("/settings", {
      service,
      routes: [
        { element: <RequireVerified />, children: [{ path: "/settings", element: <ConcurrentRequests /> }] },
        { path: "/login", element: <h1>Log in</h1> },
      ],
    });
    queryClient.setQueryData(["secret"], { phi: "x" });
    fireEvent.click(await screen.findByRole("button", { name: "Request both" }));
    await screen.findByRole("button", { name: "Requests finished" });
    expect(requests).toBe(4);
    expect(forcedRefreshes(getToken)).toBe(2);
    expect(signOut).toHaveBeenCalledTimes(1);
    releaseSignOut.resolve();
    await h1("Log in");
    expect(here(router)).toBe("/login?next=%2Fsettings");
    expect(queryClient.getQueryData(["secret"])).toBeUndefined();
    expect(await service.getToken()).toBeNull();
  });
});
