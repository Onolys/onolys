/**
 * Speaker gate (PRD R4, AC6b): the one machine guess a person confirms. One card per speaker with
 * up to three sample lines (rendered as text, never HTML). Everyone who is not the clinician counts
 * as the client. After a run (`report_ready` / `failed`) the same cards reopen with "Save and run
 * again": confirming then only changes the clinician for the next run, so a new run is started.
 */
import { Button, Card, CardContent, Label } from "@onolys/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { unwrap } from "../../api/client";
import { describeError } from "../../api/errors";
import { useApiClient } from "../../auth/useApiClient";
import { BTN, LINK_BTN, NOTE } from "../../components/classes";
import { Notice } from "../../components/Notice";
import { ErrorCard } from "../session/ErrorCard";

export interface SpeakerGateProps {
  sessionId: string;
  /** `first`: pick and go. `rerun`: after a failure, preselect the current clinician; save, then try the run again. */
  mode: "first" | "rerun";
  onDone?: () => void;
}

export function SpeakerGate({ sessionId, mode, onDone }: SpeakerGateProps) {
  const client = useApiClient();
  const speakers = useQuery({
    queryKey: ["speakers", sessionId],
    staleTime: 0,
    gcTime: 0,
    queryFn: async () => unwrap(await client.GET("/sessions/{id}/speakers", { params: { path: { id: sessionId } } })),
  });
  const [chosen, setChosen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (speakers.isPending) return <p className={NOTE}>Loading speakers…</p>;
  if (speakers.isError) {
    return (
      <Notice>
        We couldn't load the speakers.{" "}
        <Button type="button" variant="link" className={LINK_BTN} onClick={() => void speakers.refetch()}>
          Try again
        </Button>
      </Notice>
    );
  }

  const { speakers: list, clinician_speaker: current } = speakers.data;
  const selected = chosen ?? current ?? null;

  async function confirm(speaker: string, thenRun: boolean) {
    setBusy(true);
    setError(null);
    try {
      unwrap(
        await client.POST("/sessions/{id}/speakers/confirm", {
          params: { path: { id: sessionId } },
          body: { clinician_speaker: speaker },
        }),
      );
      if (thenRun) unwrap(await client.POST("/sessions/{id}/runs", { params: { path: { id: sessionId } } }));
      onDone?.();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const err = error ? describeError(error) : null;
  return (
    <section className="grid gap-4 [&_p]:m-0" aria-labelledby="speaker-gate-heading">
      <h2 id="speaker-gate-heading" className="m-0 text-xl font-semibold">Who is the clinician?</h2>
      <p className={NOTE}>
        Check the speaker labels and lines below and tell us which speaker is the clinician.
        {list.length > 2 ? " Everyone else is the client." : ""}
      </p>
      <ul className="m-0 grid list-none gap-3 p-0" aria-label="Speakers">
        {list.map((s) => (
          <li key={s.speaker}>
            <Card>
              <CardContent className="grid gap-3">
            <h3 className="m-0 text-lg font-semibold">Speaker {s.speaker}</h3>
            <ul className="m-0 grid list-disc gap-1 pl-5" aria-label={`Sample lines from speaker ${s.speaker}`}>
              {s.samples.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
            {mode === "first" ? (
              <Button type="button" className={`${BTN} justify-self-start`} disabled={busy} onClick={() => void confirm(s.speaker, false)}>
                This is the clinician
              </Button>
            ) : (
              <Label className="min-h-0 justify-self-start">
                <input
                  type="radio"
                  name="clinician-speaker"
                  className="size-4 accent-primary"
                  checked={selected === s.speaker}
                  disabled={busy}
                  onChange={() => setChosen(s.speaker)}
                />
                This is the clinician
              </Label>
            )}
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
      {err ? <ErrorCard code={err.code} reference={err.requestId} /> : null}
      {mode === "rerun" ? (
        <div className="flex flex-wrap gap-3">
          <Button
            type="button"
            className={BTN}
            disabled={busy || selected === null}
            onClick={() => selected !== null && void confirm(selected, true)}
          >
            Save and try again
          </Button>
          <Button type="button" variant="secondary" className={BTN} disabled={busy} onClick={onDone}>
            Cancel
          </Button>
        </div>
      ) : null}
    </section>
  );
}
