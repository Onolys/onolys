/**
 * New session: choose audio or a transcript, save the change goal, then upload.
 * Audio runs through the app-level uploader; transcript files go directly to the API.
 */
import { Button, Input, Label, Select, H1, NOTE, PAGE, Field } from "@onolys/common";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { unwrap } from "../../api/client";
import { ApiError, describeError } from "../../api/errors";
import { useApiClient } from "../../auth/useApiClient";
import { ratingEnabled } from "../../config";
import { issuesFromApi } from "../rating/card";
import { goalIssues, saveGoal, SetupFields } from "../rating/SetupFields";
import { ErrorCard } from "../session/ErrorCard";
import { DEFAULT_LANGUAGE, LANGUAGES } from "./config";
import { FileNotices } from "./FileNotices";
import { fileExtension, limitsNote, validateTranscriptFile } from "./precheck";
import { prepareUpload } from "./startUpload";
import { getJob } from "./uploader";
import { useFilePick } from "./useFilePick";
import { useUploadLimits } from "./useUploadLimits";

/** A 4xx the user must fix in the input (not auth, rate limit or a timeout, which a retry can clear). */
function isTerminalPrepareError(e: unknown): boolean {
  return e instanceof ApiError && e.status >= 400 && e.status < 500 && ![401, 403, 408, 409, 425, 429].includes(e.status);
}

export function NewSessionPage() {
  const client = useApiClient();
  const limits = useUploadLimits();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const from = params.get("from");

  const [source, setSource] = useState<"audio" | "transcript">("audio");
  const filePick = useFilePick(source);
  const { file, pick } = filePick;
  const [language, setLanguage] = useState<string>(DEFAULT_LANGUAGE);
  const [typedTitle, setTypedTitle] = useState<string | null>(null);
  const [goal, setGoal] = useState("");
  const [goalIssue, setGoalIssue] = useState<string | undefined>();
  const showGoal = !ratingEnabled();
  // Session ids whose final no-rating card is already stored (a retry must not PUT again).
  const goalSaved = useRef(new Set<string>());
  // The session whose goal is stored: the field locks so a later edit can't be silently dropped.
  const [savedId, setSavedId] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  // One Idempotency-Key per form instance; a changed body needs a new key (and a new session).
  const created = useRef<{ key: string; body: string; id: string } | null>(null);
  const formKey = useRef(globalThis.crypto.randomUUID());

  const previous = useQuery({
    queryKey: ["session", from],
    enabled: from !== null,
    queryFn: async () => unwrap(await client.GET("/sessions/{id}", { params: { path: { id: from ?? "" } } })),
  });
  const title = typedTitle ?? previous.data?.title ?? "";

  // Set synchronously on submit: `isPending` lags a render, so a fast double-click got through.
  const submitting = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const submit = useMutation({
    mutationFn: async (f: File) => {
      const trimmed = title.trim();
      const body = { language, ...(trimmed ? { title: trimmed } : {}) };
      const bodyKey = JSON.stringify(body);
      if (source === "transcript") await validateTranscriptFile(f); // before a session exists
      if (!created.current || created.current.body !== bodyKey) {
        const key = created.current ? globalThis.crypto.randomUUID() : formKey.current;
        const res = unwrap(
          await client.POST("/sessions", { body, params: { header: { "Idempotency-Key": key } } }),
        );
        created.current = { key, body: bodyKey, id: res.session.id };
      }
      const id = created.current.id;
      if (showGoal && !goalSaved.current.has(id)) {
        await saveGoal(client, id, goal);
        goalSaved.current.add(id);
        setSavedId(id);
      }
      try {
        if (source === "transcript") {
          unwrap(await client.PUT("/sessions/{id}/transcript", {
            params: { path: { id } },
            headers: { "Content-Type": fileExtension(f.name) === "json" ? "application/json" : "text/plain" },
            body: "",
            bodySerializer: () => f,
          }));
        } else {
          await prepareUpload(client, id, f);
        }
      } catch (e) {
        if (isTerminalPrepareError(e)) {
          // The input must change: drop the half-made session (best effort) so no orphan is left, and start clean.
          try {
            await client.DELETE("/sessions/{id}", { params: { path: { id } } });
          } catch {
            /* the server's stale check settles it */
          }
          created.current = null;
          formKey.current = globalThis.crypto.randomUUID(); // the old key would replay the deleted session
          goalSaved.current.delete(id);
          setSavedId(null);
        }
        throw e;
      }
      return id;
    },
    onSuccess: (id) => {
      if (source === "audio") void getJob(id)?.start(); // the upload runs app-level even if the form is gone
      if (mounted.current) void navigate(`/sessions/${id}`);
    },
    onError: (e) => {
      submitting.current = false;
      if (e instanceof ApiError && e.code === "rating_invalid") {
        setGoalIssue(issuesFromApi(e).change_goal ?? "Check this field.");
      }
    },
  });

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void pick(e.dataTransfer.files[0]);
  };

  const invalidGoal = submit.error instanceof ApiError && submit.error.code === "rating_invalid";
  const err = submit.error && !invalidGoal ? describeError(submit.error) : null;
  const goalOk = !showGoal || Object.keys(goalIssues(goal)).length === 0;
  const canSubmit = filePick.ready && goalOk && !submit.isPending;

  return (
    <div className={PAGE}>
      <h1 className={H1}>New session</h1>
      <form
        className="grid max-w-xl grid-cols-1 gap-4 break-words"
        onSubmit={(e) => {
          e.preventDefault();
          if (file && canSubmit && !submitting.current) {
            submitting.current = true;
            submit.mutate(file);
          }
        }}
      >
        <fieldset disabled={submit.isPending || savedId !== null} className="m-0 grid min-w-0 gap-1 border-0 p-0">
          <legend className="p-0 text-base font-semibold">Session file</legend>
          {(["audio", "transcript"] as const).map((kind) => (
            <Label key={kind}>
              <input
                type="radio"
                name="source"
                className="size-4 accent-primary"
                checked={source === kind}
                onChange={() => {
                  setSource(kind);
                  void pick(undefined);
                  submit.reset();
                }}
              />
              {kind === "audio" ? "Audio" : "Transcript"}
            </Label>
          ))}
        </fieldset>
        <div
          data-dragging={dragging || undefined}
          className="grid gap-2 rounded-md border-2 border-dashed border-border p-4 data-[dragging]:border-primary"
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <Field label={source === "audio" ? "Audio recording" : "Transcript file"}>
            {(id) => (
              <Input
                id={id}
                key={source}
                type="file"
                accept={source === "audio" ? ".mp3,.wav,.m4a,.webm,.ogg,audio/*" : ".json,.txt"}
                onChange={(e) => void pick(e.target.files?.[0])}
              />
            )}
          </Field>
          <p className={NOTE}>
            {source === "audio"
              ? `Drop a file here or choose one. mp3, wav, m4a, webm or ogg${limits ? `, ${limitsNote(limits)}` : ""}.`
              : "Drop a file here or choose one. json or txt transcript, up to 1 MB."}
          </p>
          {file ? <p className={NOTE}>{file.name}</p> : null}
        </div>

        <FileNotices pick={filePick} />

        <Field label="Language">
          {(id) => (
            <Select id={id} value={language} onChange={(e) => setLanguage(e.target.value)}>
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </Select>
          )}
        </Field>

        <Field label="Title (optional)">
          {(id) => <Input id={id} type="text" maxLength={200} value={title} onChange={(e) => setTypedTitle(e.target.value)} />}
        </Field>

        {showGoal ? (
          <SetupFields
            goal={goal}
            disabled={savedId !== null}
            onGoal={(v) => {
              setGoal(v);
              setGoalIssue(undefined);
            }}
            issue={invalidGoal ? goalIssue : undefined}
          />
        ) : null}

        {err ? <ErrorCard code={err.code} reference={err.requestId} /> : null}

        <div>
          <Button type="submit" disabled={!canSubmit}>
            {submit.isPending ? "Starting…" : "Start"}
          </Button>
        </div>
      </form>
    </div>
  );
}
