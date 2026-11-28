import { isRouteErrorResponse, useRouteError } from "react-router";
import { ErrorRecovery } from "@onolys/common";
import { recoveryDetails } from "../api/errors";

/** Page crashes keep the shell; a shell crash gets a standalone main landmark. */
export function RouteError({ standalone = false }: { standalone?: boolean }) {
  const error = useRouteError();
  const recovery = <ErrorRecovery {...recoveryDetails(error, isRouteErrorResponse(error) ? error.status : undefined)} />;
  return standalone ? <main className="mx-auto max-w-2xl p-6">{recovery}</main> : recovery;
}
