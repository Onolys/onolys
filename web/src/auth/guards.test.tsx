import { fireEvent, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { useQuery } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { server } from "../mocks/server";
import { here, renderApp } from "../test/renderApp";
import { createMemoryRouter, RouterProvider } from "react-router";
import { routes } from "../routes/routes";
import { createFakeAuthService } from "./fakeService";
import { AuthProvider } from "./AuthProvider";
import { useApiClient } from "./useApiClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { makeQueryClient } from "../queryClient";
import { RequireVerified } from "./guards";
import { useState } from "react";

const h1 = (name: string) => screen.findByRole("heading", { level: 1, name });

describe("guards", () => {
  it.each(["/new", "/sessions", "/sessions/new", "/sessions/abc", "/sessions/abc/reports/1", "/settings"])(
    "unauthenticated %s -> /login?next=",
    async (path) => {
      const { router } = renderApp(path);
      await h1("Log in");
      expect(here(router)).toBe(`/login?next=${encodeURIComponent(path)}`);
    },
  );

  it("unauthenticated users can read /sample", async () => {
    const { router } = renderApp("/sample");
    await h1("Sample report");
    expect(here(router)).toBe("/sample");
  });

  it("/sample-report redirects to /sample", async () => {
    const { router } = renderApp("/sample-report");
    await h1("Sample report");
    expect(here(router)).toBe("/sample");
  });

  it("an unverified user cannot reach / and is sent to /verify-email", async () => {
    const { router } = renderApp("/", { user: { email: "a@clinic.org", verified: false } });
    await h1("Verify your email");
    expect(here(router)).toBe("/verify-email?next=%2Fnew");
    expect(screen.queryByRole("heading", { level: 1, name: "Welcome a" })).not.toBeInTheDocument();
  });

  it("an unverified user is sent from a deep link to /verify-email keeping next", async () => {
    const { router } = renderApp("/sessions/abc", { user: { email: "a@clinic.org", verified: false } });
    await h1("Verify your email");
    expect(here(router)).toBe("/verify-email?next=%2Fsessions%2Fabc");
  });

  it("a verified user at / ends at /new", async () => {
    const { router } = renderApp("/", { user: { email: "a@clinic.org", verified: true } });
    await h1("Welcome a");
    expect(here(router)).toBe("/new");
  });

  it("a verified user reaches /sessions", async () => {
    renderApp("/sessions", { user: { email: "a@clinic.org", verified: true } });
    await h1("Sessions");
  });

  it("a verified user on /login or /verify-email is sent on", async () => {
    renderApp("/login", { user: { email: "a@clinic.org", verified: true } });
    await h1("Welcome a");
  });

  it("a signed-out user on /verify-email goes to /login", async () => {
    renderApp("/verify-email");
    await h1("Log in");
  });

  it("an unverified user can still open the sign-up/login pages' redirect to verify", async () => {
    const { router } = renderApp("/login", { user: { email: "a@clinic.org", verified: false } });
    await h1("Verify your email");
    expect(here(router)).toBe("/verify-email");
  });
});

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

function renderWithProbe(service: ReturnType<typeof createFakeAuthService>, path: string) {
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
    const service = createFakeAuthService();
    service.signedInAs("a@clinic.org", { verified: true });
    let n = 0;
    server.use(
      http.get(USAGE, () =>
        ++n === 1 ? new HttpResponse(null, { status: 401 }) : HttpResponse.json({ eval: { day: { used: 0, cap: 20, resets_at: "x" } }, interview: { day: { used: 0, cap: 5, resets_at: "x" } } }),
      ),
    );
    const { router } = renderWithProbe(service, "/settings");
    expect(await screen.findByText("status 200")).toBeInTheDocument();
    expect(service.calls.forcedRefreshes).toBe(1);
    await h1("Settings");
    expect(here(router)).toBe("/settings");
  });

  it("a second 401 signs out, clears the query cache and the guard sends to /login", async () => {
    let requests = 0;
    server.use(http.get(USAGE, () => {
      requests++;
      return new HttpResponse(null, { status: 401 });
    }));
    const service = createFakeAuthService();
    service.signedInAs("a@clinic.org", { verified: true });
    const signOut = vi.spyOn(service, "signOut");
    // Settings already requests usage; adding Probe here would create a second request.
    const { router, queryClient } = renderApp("/settings", { service });
    queryClient.setQueryData(["secret"], { phi: "x" });
    await h1("Log in");
    expect(requests).toBe(2);
    expect(service.calls.forcedRefreshes).toBe(1);
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
    const service = createFakeAuthService();
    service.signedInAs("a@clinic.org", { verified: true });
    const releaseSignOut = deferred();
    const originalSignOut = service.signOut;
    const signOut = vi.spyOn(service, "signOut").mockImplementation(async () => {
      await releaseSignOut.promise;
      await originalSignOut();
    });
    const { router, queryClient } = renderApp("/settings", {
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
    expect(service.calls.forcedRefreshes).toBe(2);
    expect(signOut).toHaveBeenCalledTimes(1);
    releaseSignOut.resolve();
    await h1("Log in");
    expect(here(router)).toBe("/login?next=%2Fsettings");
    expect(queryClient.getQueryData(["secret"])).toBeUndefined();
    expect(await service.getToken()).toBeNull();
  });
});

describe("guards while auth is loading (no SDK report yet)", () => {
  it.each(["/settings", "/login", "/verify-email"])("%s shows Loading and neither redirects nor renders content", async (path) => {
    const service = createFakeAuthService();
    service.onAuthStateChanged = () => () => {};
    const { router } = renderApp(path, { service });
    expect(await screen.findByRole("status")).toHaveTextContent("Loading…");
    expect(here(router)).toBe(path);
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
  });
});

describe("guard redirects carry next", () => {
  it("signed-out /verify-email?next= goes to /login keeping next", async () => {
    const { router } = renderApp("/verify-email?next=%2Fsettings");
    await h1("Log in");
    expect(here(router)).toBe("/login?next=%2Fsettings");
  });

  it("verified /verify-email?next= goes to next", async () => {
    const { router } = renderApp("/verify-email?next=%2Fsettings", { user: { email: "a@clinic.org", verified: true } });
    await h1("Settings");
    expect(here(router)).toBe("/settings");
  });

  it("unverified /login?next= goes to /verify-email keeping next", async () => {
    const { router } = renderApp("/login?next=%2Fsettings", { user: { email: "a@clinic.org", verified: false } });
    await h1("Verify your email");
    expect(here(router)).toBe("/verify-email?next=%2Fsettings");
  });

  it("verified /login?next= goes to next", async () => {
    const { router } = renderApp("/login?next=%2Fsettings", { user: { email: "a@clinic.org", verified: true } });
    await h1("Settings");
    expect(here(router)).toBe("/settings");
  });

  it("a signed-out visit to / goes to /login?next=/new", async () => {
    const { router } = renderApp("/");
    await h1("Log in");
    expect(here(router)).toBe("/login?next=%2Fnew");
  });
});
