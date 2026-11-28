/**
 * In-app rating card: filled while transcription runs, autosaved as a draft,
 * submitted with `final:true`. Only "Submit rating" / "No rating" satisfy the run gate.
 */
import { Button, Card, CardContent, Input, Label, Select, Textarea, LINK_BTN, NOTE, ErrorNote, Notice } from "@onolys/common";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { unwrap } from "../../api/client";
import { ApiError, describeError } from "../../api/errors";
import { useApiClient } from "../../auth/useApiClient";
import { COUNTS, GLOBALS, LIMITS } from "../../protocol/miti-items";
import { createAutosaver, type Autosaver, type SaveStatus } from "./autosave";
import {
  buildCard,
  cardToForm,
  emptyForm,
  issuesFromApi,
  localIssues,
  softCount,
  type CountForm,
  type GlobalForm,
  type Issues,
  type RatingForm,
} from "./card";

const STATUS_TEXT: Record<SaveStatus, string> = {
  idle: "",
  saving: "Saving…",
  saved: "Draft saved",
  error: "Couldn't save — retrying",
  invalid: "Draft not saved — shorten the highlighted fields",
};

type Load = "loading" | "ready" | "error";
type Submitted = null | "submitted" | "no_rating";

const ITEM = "m-0 grid min-w-0 gap-3 rounded-md border border-border p-3";
const LEGEND = "px-1 font-semibold";
const idOf = (path: string) => `rating-${path.replace(/\./g, "-")}`;
const fmt = (n: number) => n.toLocaleString("en-US");

function Field({ path, label, error, hint, children }: { path: string; label: string; error?: string; hint?: string; children: (props: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode }) {
  const id = idOf(path);
  const describedBy = [error ? `${id}-err` : null, hint ? `${id}-hint` : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className="grid gap-1">
      <Label htmlFor={id} className="min-h-0 text-base font-semibold">
        {label}
      </Label>
      {hint ? <span className={NOTE} id={`${id}-hint`}>{hint}</span> : null}
      {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}
      {error ? <span className="text-sm text-destructive" id={`${id}-err`}>{error}</span> : null}
    </div>
  );
}

function Counter({ value, limit }: { value: string; limit: number }) {
  const c = softCount(value, limit);
  return (
    <span data-over={c.over ? "true" : "false"} className="text-sm text-muted-foreground data-[over=true]:font-semibold data-[over=true]:text-destructive">
      {fmt(c.length)} / {fmt(c.limit)}
      {c.over ? ` — over the limit by ${fmt(c.length - c.limit)}; shorten it before it can be saved` : ""}
    </span>
  );
}

function Text({ path, label, value, limit, error, rows = 3, hint, onChange }: { path: string; label: string; value: string; limit: number; error?: string; rows?: number; hint?: string; onChange: (v: string) => void }) {
  return (
    <Field path={path} label={label} error={error} hint={hint}>
      {(p) => (
        <>
          <Textarea {...p} rows={rows} value={value} onChange={(e) => onChange(e.target.value)} />
          <Counter value={value} limit={limit} />
        </>
      )}
    </Field>
  );
}

export interface RatingCardProps {
  sessionId: string;
  debounceMs?: number;
  /** The rating is final: fields are shown but cannot change, and nothing is submitted. */
  readOnly?: boolean;
}

export function RatingCard({ sessionId, debounceMs = 2000, readOnly: readOnlyProp = false }: RatingCardProps) {
  const client = useApiClient();
  const [load, setLoad] = useState<Load>("loading");
  const [attempt, setAttempt] = useState(0);
  const [form, setForm] = useState<RatingForm>(emptyForm);
  const formRef = useRef(form);
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [issues, setIssues] = useState<Issues>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<Submitted>(null);
  const [busy, setBusy] = useState(false);
  // A successful submit is final: lock the card here without waiting for the status doc to say so.
  const [locked, setLocked] = useState(false);
  const readOnly = readOnlyProp || locked;
  const saver = useRef<Autosaver | null>(null);

  // Restore: draft if present, else the last final revision.
  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const data = unwrap(await client.GET("/sessions/{id}/rating", { params: { path: { id: sessionId } } }));
        if (!live) return;
        // A final rating shows what was submitted, never a stale draft.
        const draft = readOnlyProp ? undefined : data.draft;
        const next = cardToForm(draft?.card ?? data.final?.card);
        formRef.current = next;
        setForm(next);
        setSubmitted(draft ? null : data.final ? (data.final.no_rating ? "no_rating" : "submitted") : null);
        setLoad("ready");
      } catch {
        if (live) setLoad("error");
      }
    })();
    return () => {
      live = false;
    };
  }, [client, sessionId, attempt, readOnlyProp]);

  // Autosave controller: debounce, blur and page-hide flushes all go through it.
  useEffect(() => {
    const s = createAutosaver({
      delayMs: debounceMs,
      onStatus: setStatus,
      isPermanent: (e) => e instanceof ApiError && e.code === "rating_invalid",
      save: async (keepalive) => {
        try {
          unwrap(
            await client.PUT("/sessions/{id}/rating", {
              params: { path: { id: sessionId } },
              body: { final: false, card: buildCard(formRef.current) },
              keepalive,
            }),
          );
          setIssues({});
        } catch (e) {
          if (e instanceof ApiError && e.code === "rating_invalid") setIssues(issuesFromApi(e));
          throw e;
        }
      },
    });
    saver.current = s;
    const hide = () => void s.flush({ keepalive: true });
    const onVisibility = () => {
      if (document.visibilityState === "hidden") hide();
    };
    window.addEventListener("pagehide", hide);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("pagehide", hide);
      document.removeEventListener("visibilitychange", onVisibility);
      void s.flush({ keepalive: true }); // leaving the page loses nothing
      s.dispose();
      saver.current = null;
    };
  }, [client, sessionId, debounceMs]);

  const edit = useCallback((fn: (f: RatingForm) => RatingForm) => {
    const next = fn(formRef.current);
    formRef.current = next;
    setForm(next);
    saver.current?.change();
  }, []);
  const setGlobal = (id: string, patch: Partial<GlobalForm>) =>
    edit((f) => ({ ...f, globals: { ...f.globals, [id]: { ...f.globals[id], ...patch } } }));
  const setCount = (id: string, patch: Partial<CountForm>) =>
    edit((f) => ({ ...f, counts: { ...f.counts, [id]: { ...f.counts[id], ...patch } } }));

  async function submit(noRating: boolean) {
    const found = localIssues(formRef.current, { noRating });
    setIssues(found);
    if (Object.keys(found).length) {
      setFormError("Some of your rating needs a change. Check the highlighted fields.");
      return;
    }
    setFormError(null);
    setBusy(true);
    saver.current?.cancel();
    try {
      await saver.current?.flush(); // saves any pending draft edit and waits for an in-flight one
      unwrap(
        await client.PUT("/sessions/{id}/rating", {
          params: { path: { id: sessionId } },
          body: { final: true, ...(noRating ? { no_rating: true } : {}), card: buildCard(formRef.current, { noRating }) },
        }),
      );
      setSubmitted(noRating ? "no_rating" : "submitted");
      saver.current?.cancel();
      setLocked(true);
    } catch (e) {
      if (e instanceof ApiError && e.code === "rating_invalid") {
        setIssues(issuesFromApi(e));
        setFormError(describeError(e).message);
      } else {
        setFormError(describeError(e).message);
      }
    } finally {
      setBusy(false);
    }
  }

  if (load === "loading") return <p className={NOTE}>Loading your rating…</p>;
  if (load === "error") {
    return (
      <Notice>
        We couldn't load your rating.{" "}
        <Button
          type="button"
          variant="link"
          className={LINK_BTN}
          onClick={() => {
            setLoad("loading");
            setAttempt((n) => n + 1);
          }}
        >
          Try again
        </Button>
      </Notice>
    );
  }

  const err = (p: string) => issues[p];
  return (
    <Card className="max-w-2xl">
      <CardContent>
    <form
      className="grid gap-4"
      aria-labelledby="rating-heading"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void submit(false);
      }}
      onBlur={() => void saver.current?.flush()}
    >
      <h2 id="rating-heading" className="m-0 text-xl font-semibold">Your rating</h2>
      {readOnly ? (
        <p className={NOTE}>
          {submitted === "no_rating"
            ? "Saved without a rating — Onolys will score the session on its own. "
            : submitted === "submitted"
              ? "Rating submitted. "
              : ""}
          Your rating is final: it can't be changed or run again.
        </p>
      ) : (
        <>
          <p className={NOTE}>
            Fill this in while we transcribe. It saves as you type. Onolys compares it with its own reading of the session.
          </p>
          <p className={NOTE} aria-live="polite">
            {STATUS_TEXT[status]}
          </p>
        </>
      )}
      <fieldset className="m-0 grid min-w-0 gap-4 border-0 p-0" disabled={readOnly}>

      <Field path="change_goal" label="Change goal" error={err("change_goal")}>
        {(p) => <Input {...p} type="text" value={form.changeGoal} onChange={(e) => edit((f) => ({ ...f, changeGoal: e.target.value }))} />}
      </Field>
      <fieldset className={ITEM}>
        <legend className={LEGEND}>Coded from–to (optional)</legend>
        <span className={NOTE}>Only if you rated part of the recording.</span>
        <Field path="coded_span.from_s" label="Coded from (mm:ss)" error={err("coded_span")}>
          {(p) => <Input {...p} type="text" inputMode="numeric" placeholder="mm:ss" value={form.spanFrom} onChange={(e) => edit((f) => ({ ...f, spanFrom: e.target.value }))} />}
        </Field>
        <Field path="coded_span.to_s" label="Coded to (mm:ss)">
          {(p) => <Input {...p} type="text" inputMode="numeric" placeholder="mm:ss" value={form.spanTo} onChange={(e) => edit((f) => ({ ...f, spanTo: e.target.value }))} />}
        </Field>
      </fieldset>

      <h3 className="m-0 text-lg font-semibold">Global ratings</h3>
      {GLOBALS.map((g) => {
        const f = form.globals[g.id];
        const base = `globals.${g.id}`;
        return (
          <fieldset key={g.id} className={ITEM}>
            <legend className={LEGEND}>{g.label}</legend>
            <Field path={`${base}.score`} label={`${g.label} score`} error={err(`${base}.score`)}>
              {(p) => (
                <Select {...p} value={f.score} onChange={(e) => setGlobal(g.id, { score: e.target.value })}>
                  <option value="">Not rated</option>
                  {g.anchors.map((a, i) => (
                    <option key={a} value={String(i + 1)}>
                      {i + 1} — {a}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Text path={`${base}.reason`} label={`${g.label} reason`} value={f.reason} limit={LIMITS.item} error={err(`${base}.reason`)} onChange={(v) => setGlobal(g.id, { reason: v })} />
            <Field path={`${base}.example.at_s`} label={`${g.label} example time (mm:ss, optional)`} error={err(`${base}.example.at_s`)}>
              {(p) => <Input {...p} type="text" inputMode="numeric" placeholder="mm:ss" value={f.exTime} onChange={(e) => setGlobal(g.id, { exTime: e.target.value })} />}
            </Field>
            <Text path={`${base}.example.text`} label={`${g.label} example`} value={f.exText} limit={LIMITS.item} rows={2} error={err(`${base}.example.text`)} onChange={(v) => setGlobal(g.id, { exText: v })} />
          </fieldset>
        );
      })}

      <h3 className="m-0 text-lg font-semibold">Behaviour counts</h3>
      {COUNTS.map((c) => {
        const f = form.counts[c.id];
        const base = `counts.${c.id}`;
        return (
          <fieldset key={c.id} className={ITEM}>
            <legend className={LEGEND}>{c.label}</legend>
            <Field path={`${base}.count`} label={`${c.label} count`} error={err(`${base}.count`)}>
              {(p) => <Input {...p} type="number" min={0} step={1} value={f.count} onChange={(e) => setCount(c.id, { count: e.target.value })} />}
            </Field>
            <Text path={`${base}.note`} label={`${c.label} note`} value={f.note} limit={LIMITS.item} rows={2} error={err(`${base}.note`)} onChange={(v) => setCount(c.id, { note: v })} />
          </fieldset>
        );
      })}

      <Text
        path="notes"
        label="Additional notes / evaluation reasoning"
        value={form.notes}
        limit={LIMITS.notes}
        rows={6}
        error={err("notes")}
        hint="Not parsed into the card above. Onolys checks what you write here against the transcript."
        onChange={(v) => edit((f) => ({ ...f, notes: v }))}
      />

      </fieldset>

      {formError ? (
        <ErrorNote role="alert">{formError}</ErrorNote>
      ) : null}
      {submitted && !readOnly ? (
        <p className={NOTE}>
          {submitted === "submitted" ? "Rating submitted." : "Saved without a rating — Onolys will score the session on its own."}
        </p>
      ) : null}
      {readOnly ? null : (
        <div className="flex flex-wrap gap-3">
          <Button type="submit" disabled={busy}>
            Submit rating
          </Button>
          <Button type="button" variant="secondary" disabled={busy} onClick={() => void submit(true)}>
            No rating — just rate my session
          </Button>
        </div>
      )}
    </form>
      </CardContent>
    </Card>
  );
}
