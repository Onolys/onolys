import type { ReactNode } from "react";
import "./ui.css";

/** Secondary text: caveats, footnotes. Muted and small; place below the content it qualifies. */
export function Note({ children }: { children: ReactNode }) {
  return <p className="ui-note">{children}</p>;
}
