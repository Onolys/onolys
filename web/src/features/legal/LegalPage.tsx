import type { ReactNode } from "react";

export const LEGAL_UPDATED = "2026-11-23";

/** Shared shell for the Privacy Policy and Terms of Service pages: h1 and updated date. The document title stays static (hosting/privacy.test.ts forbids assigning it). */
export function LegalPage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <article className="legal">
      <h1>{title}</h1>
      <p className="legal-updated">Last updated: {LEGAL_UPDATED}</p>
      {children}
    </article>
  );
}
