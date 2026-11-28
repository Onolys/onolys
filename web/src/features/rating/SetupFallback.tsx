/**
 * Session-page fallback: a session that never got its change goal (created before this
 * build, or an interview whose PUT failed) sets it here. Same field as the upload screen; the
 * "Continue" button only does the final no-rating `PUT /rating` (409 `rating_final` = done).
 */
import { Button, ErrorNote } from "@onolys/common";
import { useEffect, useState } from "react";
import { unwrap } from "../../api/client";
import { ApiError, describeError } from "../../api/errors";
import { useApiClient } from "../../auth/useApiClient";
import { cardToForm, issuesFromApi } from "./card";
import { goalIssues, saveGoal, SetupFields } from "./SetupFields";

export function SetupFallback({ sessionId }: { sessionId: string }) {
  const client = useApiClient();
  const [goal, setGoal] = useState("");
  const [issue, setIssue] = useState<string | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Prefill from the draft (or last final) once; never overwrite what the user already typed.
  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const data = unwrap(await client.GET("/sessions/{id}/rating", { params: { path: { id: sessionId } } }));
        const g = cardToForm(data.draft?.card ?? data.final?.card).changeGoal;
        if (live && g) setGoal((cur) => (cur === "" ? g : cur));
      } catch {
        /* no draft: the field stays empty */
      }
    })();
    return () => {
      live = false;
    };
  }, [client, sessionId]);

  const onContinue = async (e: { preventDefault: () => void }) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    const local = goalIssues(goal);
    if (local.change_goal) {
      setIssue(local.change_goal);
      return;
    }
    setIssue(undefined);
    setBusy(true);
    try {
      await saveGoal(client, sessionId, goal);
    } catch (err) {
      if (err instanceof ApiError && err.code === "rating_invalid") setIssue(issuesFromApi(err).change_goal ?? "Check this field.");
      else setError(describeError(err).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="grid gap-3" onSubmit={(e) => void onContinue(e)} noValidate>
      <SetupFields goal={goal} onGoal={(v) => setGoal(v)} issue={issue} />
      {error ? <ErrorNote role="alert">{error}</ErrorNote> : null}
      <div>
        <Button type="submit" disabled={busy}>
          Continue
        </Button>
      </div>
    </form>
  );
}
