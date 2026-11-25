import { Button } from "@onolys/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useNavigate } from "react-router";
import { unwrap } from "../../api/client";
import { describeError } from "../../api/errors";
import { useApiClient } from "../../auth/useApiClient";
import { dropJob } from "../upload/uploader";
import { DeleteDialog } from "./DeleteDialog";
import { ErrorCard } from "./ErrorCard";

/**
 * "Delete session" button + confirm dialog + DELETE call + return to the sessions list. Shared by the
 * report page and the terminal failed / cancelled views. `onBusyChange` lets a live view hold its
 * status updates while the DELETE is in flight.
 */
export function DeleteSession({ id, onBusyChange }: { id: string; onBusyChange?: (busy: boolean) => void }) {
  const client = useApiClient();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const remove = useMutation({
    mutationFn: async () => unwrap(await client.DELETE("/sessions/{id}", { params: { path: { id } } })),
    onMutate: () => onBusyChange?.(true),
    onError: () => onBusyChange?.(false),
    onSuccess: () => {
      dropJob(id);
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
      void navigate("/sessions");
    },
  });
  const error = remove.error ? describeError(remove.error) : null;
  return (
    <>
      <div className="border-t border-border pt-6">
        <Button ref={button} type="button" variant="secondary" onClick={() => setConfirming(true)}>
          Delete session
        </Button>
      </div>
      <DeleteDialog
        open={confirming}
        busy={remove.isPending}
        onConfirm={() => remove.mutate()}
        onCancel={() => {
          setConfirming(false);
          remove.reset();
        }}
        onClosed={() => button.current?.focus()}
      >
        {error ? <ErrorCard code={error.code} reference={error.requestId} /> : null}
      </DeleteDialog>
    </>
  );
}
