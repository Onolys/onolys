import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { AuthProvider } from "../auth/AuthProvider";
import { createFakeAuthService } from "../auth/fakeService";
import { makeQueryClient } from "../queryClient";
import type { RenderOptions } from "./renderApp";

/** Renders one page element directly (no app routes/layout) at `path`; other paths render a stub. */
export function renderPage(element: ReactElement, path: string, opts: RenderOptions = {}) {
  const service = opts.service ?? createFakeAuthService();
  if (opts.user) service.signedInAs(opts.user.email, { verified: opts.user.verified });
  const router = createMemoryRouter(
    [
      { path: path, element: <main>{element}</main> },
      { path: "*", element: <main>elsewhere</main> },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <AuthProvider service={service}>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>,
  );
  return { router, service };
}
