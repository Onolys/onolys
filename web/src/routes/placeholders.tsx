import type { ReactNode } from "react";
import { Link } from "react-router";
import { useAuth } from "../auth/AuthProvider";

const LINK = "text-primary underline underline-offset-4";

function Page({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <>
      <h1 className="text-2xl font-semibold">{title}</h1>
      {children ?? <p className="mt-4">This page is a placeholder.</p>}
    </>
  );
}

export function NotFound() {
  const { phase } = useAuth();
  return (
    <Page title="Page not found">
      {phase === "verified" && (
        <p className="mt-4">
          <Link to="/sessions" className={LINK}>Back to your sessions</Link>
        </p>
      )}
      {phase === "unverified" && (
        <p className="mt-4">
          <Link to="/verify-email" className={LINK}>Verify your email</Link>
        </p>
      )}
      {phase === "signedOut" && (
        <p className="mt-4">
          <Link to="/login" className={LINK}>Log in</Link>
        </p>
      )}
    </Page>
  );
}
