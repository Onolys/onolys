import { Button } from "@onolys/ui";
import { Link } from "react-router";
import { messageForCode } from "../../api/errors";
import { ErrorCard } from "./ErrorCard";

/**
 * A file that failed validation is an upload failure, not a session (PRD R11): the session is gone,
 * only a data-free status stub remains. The reason is the existing per-code copy.
 */
export function UploadFailedView({ code, reference }: { code: string | null | undefined; reference: string }) {
  const reason = messageForCode(code ?? undefined).replace(/\.$/, "");
  return (
    <ErrorCard code={code ?? undefined} message={`Upload failed: ${reason}. Choose a different file.`} reference={reference}>
      <Button asChild>
        <Link to="/sessions/new">Choose a different file</Link>
      </Button>
    </ErrorCard>
  );
}
