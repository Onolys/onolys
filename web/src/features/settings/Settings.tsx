/** `/settings` (PRD R6, D9): API key management, usage, sign out, account-removal contact. */
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  Checkbox,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Label,
} from "@onolys/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { unwrap } from "../../api/client";
import { describeError } from "../../api/errors";
import { useSignOut } from "../../auth/useSignOut";
import { useApiClient } from "../../auth/useApiClient";
import { ACTIONS, H1, LINK, NOTE } from "../../components/classes";
import { CONTACT_EMAIL } from "../../config";
import { formatResetTime } from "../../lib/format";
import { UsageLeft } from "../usage/UsageLeft";
import { useUsage } from "../usage/useUsage";
import { ErrorCard } from "../session/ErrorCard";

const DOCS_URL = "/v1/docs";
const H2 = "m-0 text-xl font-semibold";
const SECTION = "grid gap-3";
const when = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString() : "never");

type Confirm = "regenerate" | "revoke" | null;

export function Settings() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const { signOut, error: signOutError } = useSignOut();
  const key = useQuery({ queryKey: ["api-key"], queryFn: async () => unwrap(await client.GET("/api-key")) });
  const usage = useUsage();
  const usageErr = usage.error ? describeError(usage.error) : null;

  const [confirm, setConfirm] = useState<Confirm>(null);
  const regenerateBtn = useRef<HTMLButtonElement>(null);
  const revokeBtn = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // The one-time secret lives only here (dialog state): not in the query cache, storage or logs.
  const [secret, setSecret] = useState<string | null>(null);
  const [stored, setStored] = useState(false);
  const [copy, setCopy] = useState<"idle" | "copied" | "failed">("idle");

  const copySecret = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopy("copied");
    } catch {
      setCopy("failed");
    }
  };

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setConfirm(null);
    } catch (e) {
      // Keep the confirm dialog open so the error is seen where the user acted.
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const create = () =>
    run(async () => {
      const created = unwrap(await client.POST("/api-key"));
      setStored(false);
      setSecret(created.api_key);
      await queryClient.invalidateQueries({ queryKey: ["api-key"] });
    });
  const revoke = () =>
    run(async () => {
      unwrap(await client.DELETE("/api-key"));
      await queryClient.invalidateQueries({ queryKey: ["api-key"] });
    });
  const dismissSecret = () => {
    setSecret(null);
    setStored(false);
    setCopy("idle");
  };
  const closeConfirm = () => {
    setConfirm(null);
    setError(null);
  };

  const info = key.data;
  const err = error ? describeError(error) : null;
  const removal = <a className={LINK} href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>;

  return (
    <div className="grid gap-6">
      <h1 className={H1}>Settings</h1>

      <section aria-labelledby="key-h" className={SECTION}>
        <h2 id="key-h" className={H2}>
          API key
        </h2>
        {key.isPending ? <p className={NOTE}>Loading…</p> : null}
        {key.isError ? <ErrorCard code={describeError(key.error).code} reference={describeError(key.error).requestId} /> : null}
        {err && !confirm ? <ErrorCard code={err.code} reference={err.requestId} /> : null}
        {info && !info.active ? (
          <>
            <p>No API key yet.</p>
            <div className={ACTIONS}>
              <Button type="button" disabled={busy} onClick={() => void create()}>
                Create API key
              </Button>
            </div>
          </>
        ) : null}
        {info?.active ? (
          <>
            <dl className="m-0 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 [&_dd]:m-0">
              <dt className="font-semibold">Key</dt>
              <dd>
                <code>onolys_{info.key_id}_…</code>
              </dd>
              <dt className="font-semibold">Status</dt>
              <dd>Active</dd>
              <dt className="font-semibold">Created</dt>
              <dd>{when(info.created)}</dd>
              <dt className="font-semibold">Last used</dt>
              <dd>{when(info.last_used_at)}</dd>
            </dl>
            <div className={ACTIONS}>
              <Button ref={regenerateBtn} type="button" variant="secondary" disabled={busy} onClick={() => setConfirm("regenerate")}>
                Regenerate
              </Button>
              <Button ref={revokeBtn} type="button" variant="secondary" disabled={busy} onClick={() => setConfirm("revoke")}>
                Revoke
              </Button>
            </div>
          </>
        ) : null}
        <h3 className="m-0 mt-2 text-lg font-semibold">Use the API</h3>
        <p>
          <a className={LINK} href={DOCS_URL}>
            API docs
          </a>
        </p>
        <pre className="m-0 overflow-x-auto rounded-md border border-border bg-muted p-3 text-sm">
          <code>{`curl -H "X-API-Key: onolys_<id>_<secret>" ${window.location.origin}/v1/usage`}</code>
        </pre>
      </section>

      <section aria-labelledby="usage-h" className={SECTION}>
        <h2 id="usage-h" className={H2}>
          Usage
        </h2>
        {usage.data ? (
          <>
            <p>
              Ratings: <UsageLeft kind="eval" period="day" />
              {formatResetTime(usage.data.eval.day.resets_at)
                ? `. Daily limit resets at ${formatResetTime(usage.data.eval.day.resets_at)}`
                : ""}
            </p>
            <p>
              Interviews: <UsageLeft kind="interview" period="day" />
            </p>
          </>
        ) : usage.isError ? (
          <ErrorCard code={usageErr?.code} reference={usageErr?.requestId} message="We couldn't load your usage.">
            <Button type="button" variant="secondary" onClick={() => void usage.refetch()}>
              Retry
            </Button>
          </ErrorCard>
        ) : (
          <p className={NOTE}>Loading…</p>
        )}
      </section>

      <section aria-labelledby="account-h" className={SECTION}>
        <h2 id="account-h" className={H2}>
          Account
        </h2>
        <p>
          Deleting a session removes its audio, transcript, rating and reports. For account removal, contact {removal}.
        </p>
        <div className={ACTIONS}>
          <Button type="button" variant="secondary" onClick={() => void signOut()}>
            Sign out
          </Button>
        </div>
        {signOutError && <p role="alert">{signOutError}</p>}
      </section>

      <AlertDialog
        open={confirm === "regenerate"}
        onOpenChange={(next) => {
          if (!next) closeConfirm();
        }}
      >
        <AlertDialogContent
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            regenerateBtn.current?.focus();
          }}
        >
          <AlertDialogHeader>
            <AlertDialogTitle>Regenerate API key?</AlertDialogTitle>
            <AlertDialogDescription>
              The old key stops working immediately. Anything using it must be updated with the new key.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {err ? <ErrorCard code={err.code} reference={err.requestId} /> : null}
          <AlertDialogFooter>
            <AlertDialogCancel variant="secondary">
              Cancel
            </AlertDialogCancel>
            <Button type="button" disabled={busy} onClick={() => void create()}>
              Regenerate key
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={confirm === "revoke"}
        onOpenChange={(next) => {
          if (!next) closeConfirm();
        }}
      >
        <AlertDialogContent
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            revokeBtn.current?.focus();
          }}
        >
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke API key?</AlertDialogTitle>
            <AlertDialogDescription>The key stops working immediately. You can create a new one later.</AlertDialogDescription>
          </AlertDialogHeader>
          {err ? <ErrorCard code={err.code} reference={err.requestId} /> : null}
          <AlertDialogFooter>
            <AlertDialogCancel variant="secondary">
              Cancel
            </AlertDialogCancel>
            <Button type="button" variant="destructive" disabled={busy} onClick={() => void revoke()}>
              Revoke key
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* One-time secret: no Escape, no outside click, no close button; only "Done" (after the stored checkbox) dismisses. */}
      <Dialog open={secret !== null}>
        <DialogContent
          data-testid="api-secret-dialog"
          showCloseButton={false}
          onEscapeKeyDown={(e) => e.preventDefault()}
          onPointerDownOutside={(e) => e.preventDefault()}
          onInteractOutside={(e) => e.preventDefault()}
        >
          <DialogHeader>
            <DialogTitle>Your new API key</DialogTitle>
            <DialogDescription>Copy it now. It is shown only once and can't be retrieved later.</DialogDescription>
          </DialogHeader>
          <code data-testid="api-secret" className="break-all rounded-md border border-border bg-muted p-3 text-sm">
            {secret}
          </code>
          <div className={ACTIONS}>
            <Button type="button" variant="secondary" onClick={() => void copySecret(secret ?? "")}>
              Copy
            </Button>
            <span role="status" className={NOTE}>
              {copy === "copied" ? "Copied" : copy === "failed" ? "Couldn't copy. Select the key and copy it by hand." : ""}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Checkbox id="secret-stored" checked={stored} onCheckedChange={(v) => setStored(v === true)} />
            <Label htmlFor="secret-stored">I've stored it</Label>
          </div>
          <DialogFooter>
            <Button type="button" disabled={!stored} onClick={dismissSecret}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
