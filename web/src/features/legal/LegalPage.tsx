import { useEffect, type ReactNode } from "react";

export const LEGAL_UPDATED = "2026-11-23";

/** Shared shell for the Privacy Policy and Terms of Service pages: h1, updated date, document title. */
export function LegalPage({ title, children }: { title: string; children: ReactNode }) {
  useEffect(() => {
    document.title = `${title} | Onolys`;
  }, [title]);
  return (
    <article className="legal">
      <h1>{title}</h1>
      <p className="legal-updated">Last updated: {LEGAL_UPDATED}</p>
      {children}
    </article>
  );
}
