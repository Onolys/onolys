/**
 * `/interviews/new`: pick a practice scenario and a voice, read the headphone tip, check the
 * microphone, then start. Starting reserves one interview unit and opens the live page.
 */
import { Badge, Button, Label, Select, Skeleton, ACTIONS, H1, LINK, LINK_BTN, NOTE, PAGE, Field, ErrorNote, Notice } from "@onolys/common";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { pageLoadError } from "../../pageLoadError";
import { unwrap } from "../../api/client";
import { describeError } from "../../api/errors";
import { useApiClient } from "../../auth/useApiClient";
import { ErrorCard } from "../session/ErrorCard";
import { UsageBar } from "../usage/UsageBar";
import { blockingPeriod } from "../usage/usage";
import { USAGE_KEY, useUsage } from "../usage/useUsage";
import { interviewCapText } from "./capText";

type MicCheck = "idle" | "checking" | "ok" | "denied";

export function NewInterviewPage() {
  const client = useApiClient();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const scenarios = useQuery({
    queryKey: ["scenarios"],
    throwOnError: pageLoadError,
    queryFn: async () => unwrap(await client.GET("/scenarios")),
  });
  const usage = useUsage();
  const blocking = blockingPeriod(usage.data, "interview");

  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [voice, setVoice] = useState<string | null>(null);
  const [mic, setMic] = useState<MicCheck>("idle");

  const list = scenarios.data?.scenarios ?? [];
  const chosen = scenarioId ?? list[0]?.id ?? null;
  const chosenVoice = voice ?? list.find((s) => s.id === chosen)?.voice ?? "";

  const checkMic = async () => {
    setMic("checking");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      setMic("ok");
    } catch {
      setMic("denied");
    }
  };

  const start = useMutation({
    mutationFn: async () =>
      unwrap(
        await client.POST("/interviews", {
          body: { scenario_id: chosen ?? "", voice: chosenVoice },
        }),
      ),
    onSuccess: (interview) => {
      void queryClient.invalidateQueries({ queryKey: USAGE_KEY });
      void navigate(`/interviews/${interview.interview_id}`, { state: { interview } });
    },
    onError: () => void queryClient.invalidateQueries({ queryKey: USAGE_KEY }),
  });

  if (scenarios.isPending)
    return (
      <div className={PAGE} aria-busy="true">
        <h1 className={H1}>AI interview</h1>
        <p className={NOTE}>Loading scenarios…</p>
        <Skeleton className="h-16 w-full max-w-xl" />
        <Skeleton className="h-16 w-full max-w-xl" />
      </div>
    );
  if (scenarios.isError) {
    const e = describeError(scenarios.error);
    return (
      <div className={PAGE}>
        <h1 className={H1}>AI interview</h1>
        <ErrorCard code={e.code} reference={e.requestId}>
          <Button type="button" variant="link" className={LINK_BTN} onClick={() => void scenarios.refetch()}>
            Try again
          </Button>
        </ErrorCard>
      </div>
    );
  }

  const err = start.error ? describeError(start.error) : null;

  return (
    <div className={PAGE}>
      <h1 className={H1}>AI interview</h1>
      <p className={NOTE}>Practise a motivational interview with an AI client, then get it rated like any recording.</p>
      <div className="max-w-xl">
        <UsageBar kind="interview" label="AI interviews" />
      </div>
      <form
        className="grid max-w-xl grid-cols-1 gap-4 break-words"
        onSubmit={(e) => {
          e.preventDefault();
          if (chosen && !blocking && !start.isPending) start.mutate();
        }}
      >
        <fieldset className="m-0 grid min-w-0 gap-2 border-0 p-0">
          <legend className="p-0 pb-1 text-base font-semibold">Scenario</legend>
          {list.map((s) => (
            <Label key={s.id} className="items-start rounded-md border border-border p-3 has-[:checked]:border-primary">
              <input
                type="radio"
                name="scenario"
                className="mt-1 size-4 shrink-0 accent-primary"
                checked={chosen === s.id}
                onChange={() => {
                  setScenarioId(s.id);
                  setVoice(null); // the picker follows the scenario's own voice
                }}
              />{" "}
              <span className="block leading-normal">
                <strong>{s.title}</strong> <Badge variant="outline">{s.difficulty}</Badge>
                <span className={`${NOTE} block font-normal`}> {s.summary}</span>
              </span>
            </Label>
          ))}
        </fieldset>

        <Field label="Voice">
          {(id) => (
            <Select id={id} value={chosenVoice} onChange={(e) => setVoice(e.target.value)}>
              {(scenarios.data?.voices ?? []).map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </Select>
          )}
        </Field>

        <Notice>Use headphones: the AI's voice would otherwise leak into your microphone and be recorded twice.</Notice>

        <div className={ACTIONS}>
          <Button type="button" variant="outline" onClick={() => void checkMic()} disabled={mic === "checking"}>
            Test microphone
          </Button>
          {mic === "ok" ? <span role="status">Microphone works.</span> : null}
        </div>
        {mic === "denied" ? (
          <ErrorNote role="alert">We couldn't use your microphone. Allow it in your browser's site settings and test again.</ErrorNote>
        ) : null}

        {blocking ? <Notice>{interviewCapText(blocking)}</Notice> : null}
        {err ? <ErrorCard code={err.code} reference={err.requestId} /> : null}

        <div className={ACTIONS}>
          <Button type="submit" disabled={!chosen || blocking !== null || start.isPending}>
            {start.isPending ? "Starting…" : "Start interview"}
          </Button>
          <Link to="/new" className={LINK}>
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
