import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router";
import { AuthProvider } from "../auth/AuthProvider";
import { createFakeAuthService, type FakeAuthService } from "../auth/fakeService";
import { clearJobs } from "../features/upload/uploader";
import { makeQueryClient } from "../queryClient";
import { routes } from "../routes/routes";

export interface RenderOptions {
  service?: FakeAuthService;
  /** Pre-signed-in user. Omit for signed out. */
  user?: { email: string; verified: boolean; displayName?: string | null };
  /** Route table to render instead of the app routes (page-level tests). */
  routes?: RouteObject[];
}

export function renderApp(path: string, opts: RenderOptions = {}) {
  const service = opts.service ?? createFakeAuthService();
  if (opts.user) service.signedInAs(opts.user.email, { verified: opts.user.verified, displayName: opts.user.displayName });
  const queryClient = makeQueryClient();
  const router = createMemoryRouter(opts.routes ?? routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider service={service} onSignOut={clearJobs}>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  );
  return { router, service, queryClient };
}

export function here(router: { state: { location: { pathname: string; search: string } } }) {
  return router.state.location.pathname + router.state.location.search;
}
