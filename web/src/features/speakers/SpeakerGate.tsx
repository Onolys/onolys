/**
 * Speaker gate: the one machine guess a person confirms. One card per speaker with
 * up to three sample lines (rendered as text, never HTML). Everyone who is not the clinician counts
 * as the client. A successful confirmation keeps the controls locked until the status doc moves on,
 * so a second call cannot race the first.
 */
import { Button, Card, CardContent } from "@onolys/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { unwrap } from "../../api/client";
import { describeError } from "../../api/errors";
import { useApiClient } from "../../auth/useApiClient";
import { LINK_BTN, NOTE } from "../../components/classes";
import { Notice } from "../../components/Notice";
import { ErrorCard } from "../session/ErrorCard";

export interface SpeakerGateProps {
  sessionId: string;
}

/** An opaque diarization id (`spk_0`) reads as "Speaker 1"; a label the transcript really carries (a name) is kept. Nothing is invented. */
const speakerLabel = (speaker: string, index: number) => (/^spk_\d+$/.test(speaker) ? `Speaker ${index + 1}` : `Speaker ${speaker}`);

export function SpeakerGate({ sessionId }: SpeakerGateProps) {
  const client = useApiClient();
  const speakers = useQuery({
    queryKey: ["speakers", sessionId],
    staleTime: 0,
    gcTime: 0,
    queryFn: async () => unwrap(await client.GET("/sessions/{id}/speakers", { params: { path: { id: sessionId } } })),
  });
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

  const { speakers: list } = speakers.data;

  async function confirm(speaker: string) {
    setBusy(true);
    setError(null);
    try {
      unwrap(
        await client.POST("/sessions/{id}/speakers/confirm", {
          params: { path: { id: sessionId } },
          body: { clinician_speaker: speaker },
        }),
      );
      // Stay locked: the status doc moving on (speaker_confirmed / running) removes the gate.
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }

  const err = error ? describeError(error) : null;
  return (
    <section className="grid gap-4" aria-labelledby="speaker-gate-heading">
      <h2 id="speaker-gate-heading" className="m-0 text-xl font-semibold">Who is the clinician?</h2>
      <p className={NOTE}>
        Check the speaker labels and lines below and tell us which speaker is the clinician.
        {list.length > 2 ? " Everyone else is the client." : ""}
      </p>
      <ul className="m-0 grid list-none gap-3 p-0" aria-label="Speakers">
        {list.map((s, n) => (
          <li key={s.speaker}>
            <Card>
              <CardContent className="grid gap-3">
            <h3 className="m-0 text-lg font-semibold">{speakerLabel(s.speaker, n)}</h3>
            <ul className="m-0 grid list-disc gap-1 pl-5" aria-label={`Sample lines from ${speakerLabel(s.speaker, n).toLowerCase()}`}>
              {s.samples.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
            <Button type="button" className="justify-self-start" disabled={busy} onClick={() => void confirm(s.speaker)}>
              This is the clinician
            </Button>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
      {err ? <ErrorCard code={err.code} reference={err.requestId} /> : null}
    </section>
  );
}
