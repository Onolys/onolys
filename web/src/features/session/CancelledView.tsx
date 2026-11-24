import { Button } from "@onolys/ui";
import type { Ref } from "react";
import { ACTIONS } from "../../components/classes";

/**
 * Terminal view of a cancelled session (04-cancel R9): heading, whether it counted toward the limit
 * (`counted` null/undefined omits the sentence) and Delete. No rating, speaker gate or retry.
 */
export function CancelledView({
  counted,
  onDelete,
  deleteRef,
}: {
  counted: boolean | null | undefined;
  onDelete: () => void;
  deleteRef?: Ref<HTMLButtonElement>;
}) {
  return (
    <>
      <h2 className="text-xl font-semibold">Cancelled</h2>
      {counted == null ? null : (
        <p role="status">
          Session cancelled. {counted ? "This counted toward your limit." : "This did not count toward your limit."}
        </p>
      )}
      <div className={ACTIONS}>
        <Button ref={deleteRef} type="button" variant="secondary" onClick={onDelete}>
          Delete session
        </Button>
      </div>
    </>
  );
}
