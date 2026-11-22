import type { ReactNode } from "react";
import { Link } from "react-router";
import { useAuth } from "../auth/AuthProvider";

function Page({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <>
      <h1>{title}</h1>
      {children ?? <p>This page is a placeholder.</p>}
    </>
  );
}

export function NotFound() {
  const { phase } = useAuth();
  return (
    <Page title="Page not found">
      {phase === "verified" && (
        <p>
          <Link to="/">Back to your sessions</Link>
        </p>
      )}
      {phase === "unverified" && (
        <p>
          <Link to="/verify-email">Verify your email</Link>
        </p>
      )}
      {phase === "signedOut" && (
        <p>
          <Link to="/login">Log in</Link>
        </p>
      )}
    </Page>
  );
}
