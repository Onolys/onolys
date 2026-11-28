import { Card, CardContent, Separator } from "@onolys/common";
import type { ReactNode } from "react";

export const LEGAL_UPDATED = "2026-11-23";

/** Shared shell for the Privacy Policy and Terms of Service pages: h1 and updated date. The document title stays static (hosting/privacy.test.ts forbids assigning it). */
export function LegalPage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card className="mx-auto w-full max-w-[44rem]">
      <CardContent>
        <article className="grid gap-3 [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-4 [&_h2]:m-0 [&_h2]:mt-4 [&_h2]:text-xl [&_h2]:font-semibold [&_li]:m-0 [&_ul]:m-0 [&_ul]:grid [&_ul]:list-disc [&_ul]:gap-1 [&_ul]:pl-6">
          <h1 className="m-0 text-2xl font-semibold">{title}</h1>
          <p className="text-muted-foreground">Last updated: {LEGAL_UPDATED}</p>
          <Separator />
          {children}
        </article>
      </CardContent>
    </Card>
  );
}
