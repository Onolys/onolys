import type { ReactElement } from "react";
import { renderApp, type RenderOptions } from "./renderApp";

/** Renders one page element directly (no app routes/layout) at `path`; other paths render a stub. */
export function renderPage(element: ReactElement, path: string, opts: RenderOptions = {}) {
  return renderApp(path, {
    ...opts,
    routes: [
      { path, element: <main>{element}</main> },
      { path: "*", element: <main>elsewhere</main> },
    ],
  });
}
