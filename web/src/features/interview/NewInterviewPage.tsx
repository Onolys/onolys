/**
 * `/interviews/new` (SP10 R8, D16): pick a practice scenario and a voice, read the headphone tip, check the
 * microphone, then start. Starting reserves one interview unit and opens the live page.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { unwrap } from "../../api/client";
import { describeError } from "../../api/errors";
import { useApiClient } from "../../auth/useApiClient";
import { ErrorCard } from "../session/ErrorCard";
import { UsageLeft } from "../usage/UsageLeft";
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

  if (scenarios.isPending) return <><h1>AI interview</h1><p className="form-note">Loading scenarios…</p></>;
  if (scenarios.isError) {
    const e = describeError(scenarios.error);
    return (
      <>
        <h1>AI interview</h1>
        <ErrorCard code={e.code} reference={e.requestId}>
          <button type="button" className="link-button" onClick={() => void scenarios.refetch()}>
            Try again
          </button>
        </ErrorCard>
      </>
    );
  }

  const err = start.error ? describeError(start.error) : null;

  return (
    <>
      <h1>AI interview</h1>
      <p className="form-note">
        Practise a motivational interview with an AI client, then get it rated like any recording.{" "}
        <UsageLeft kind="interview" period="day" />
      </p>
      <form
        className="auth-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (chosen && !blocking && !start.isPending) start.mutate();
        }}
      >
        <fieldset>
          <legend>Scenario</legend>
          {list.map((s) => (
            <label key={s.id} className="scenario-option">
              <input type="radio" name="scenario" checked={chosen === s.id} onChange={() => {
                  setScenarioId(s.id);
                  setVoice(null); // the picker follows the scenario's own voice
                }} />{" "}
              <strong>{s.title}</strong> <span className="chip">{s.difficulty}</span>
              <span className="form-note"> {s.summary}</span>
            </label>
          ))}
        </fieldset>

        <label>
          Voice
          <select value={chosenVoice} onChange={(e) => setVoice(e.target.value)}>
            {(scenarios.data?.voices ?? []).map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>

        <p className="notice">Use headphones: the AI's voice would otherwise leak into your microphone and be recorded twice.</p>

        <p>
          <button type="button" className="btn btn-secondary" onClick={() => void checkMic()} disabled={mic === "checking"}>
            Test microphone
          </button>{" "}
          {mic === "ok" ? <span role="status">Microphone works.</span> : null}
          {mic === "denied" ? (
            <span role="alert" className="form-error">
              We couldn't use your microphone. Allow it in your browser's site settings and test again.
            </span>
          ) : null}
        </p>

        {blocking ? <p className="notice">{interviewCapText(blocking)}</p> : null}
        {err ? <ErrorCard code={err.code} reference={err.requestId} /> : null}

        <p>
          <button type="submit" className="btn btn-primary" disabled={!chosen || blocking !== null || start.isPending}>
            {start.isPending ? "Starting…" : "Start interview"}
          </button>{" "}
          <Link to="/">Cancel</Link>
        </p>
      </form>
    </>
  );
}
