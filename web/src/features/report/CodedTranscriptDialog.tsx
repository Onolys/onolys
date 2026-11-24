/**
 * Coded transcript dialog (SP2): a native modal <dialog> with the Utt # | Speaker | Utterance |
 * Code(s) | Why table. `CodedTranscriptProvider` is mounted only by ReportView, which builds the
 * rows once and passes them in; it owns the dialog and exposes `open(n?)` through context so
 * ReportView's button and every UtteranceLink open it.
 */
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CodedRow, TurnsState } from "./codedRows";
import { CODE_META, SHORT } from "./codeMeta";
import { Badge, Button, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@onolys/ui";
import { LINK_BTN, NOTE } from "../../components/classes";
import { CodeChip, PLAIN_CODE } from "./CodeChip";
import { CodedDialogContext } from "./codedDialogContext";

export interface CodedTranscriptProviderProps {
  turns: TurnsState;
  /** Built once by ReportView (empty until the transcript is ready). */
  rows: readonly CodedRow[];
  /** Number of practitioner utterances in `rows`. */
  practitioner: number;
  /** Distinct code ids for the legend, in report order. */
  legendIds: readonly string[];
  /** Show the "Not coded" legend entry (sample only). */
  showNotCodedLegend?: boolean;
  children: ReactNode;
}

const TH = "text-xs font-semibold uppercase tracking-wider text-muted-foreground";
const CELL = "whitespace-normal align-top";
// Below 640px the table is too wide for the screen and the Why column is cut off, so each row becomes a stacked block
// whose cells carry their column name (data-label, shown by ::before); the header row stays for screen readers only.
const STACK_CELL = `${CELL} max-[640px]:block max-[640px]:empty:hidden max-[640px]:px-0 max-[640px]:py-0.5 max-[640px]:before:mr-2 max-[640px]:before:text-xs max-[640px]:before:font-semibold max-[640px]:before:uppercase max-[640px]:before:text-muted-foreground max-[640px]:before:content-[attr(data-label)]`;
const HIGHLIGHT_MS = 1500;
const prefersReducedMotion = () =>
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function CodedTranscriptProvider({
  turns,
  rows,
  practitioner,
  legendIds,
  showNotCodedLegend,
  children,
}: CodedTranscriptProviderProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [req, setReq] = useState<{ id: number; n?: number } | null>(null);
  const counter = useRef(0);

  const open = useCallback((n?: number) => {
    if (!dialogRef.current?.open)
      opener.current = document.activeElement as HTMLElement | null;
    counter.current += 1;
    setReq({ id: counter.current, n });
  }, []);

  // Show the modal and scroll after the render that carries the request.
  useEffect(() => {
    const dlg = dialogRef.current;
    if (!req || !dlg) return;
    if (!dlg.open) {
      dlg.showModal();
      document.documentElement.classList.add("dlg-open");
    }
    clearTimeout(timer.current);
    dlg.querySelectorAll("tr.hl").forEach((r) => r.classList.remove("hl"));
    if (req.n === undefined) {
      if (bodyRef.current) bodyRef.current.scrollTop = 0;
      return;
    }
    const row = document.getElementById(`utt-${req.n}`);
    if (!row) return;
    row.scrollIntoView({
      block: "center",
      behavior: prefersReducedMotion() ? "auto" : "smooth",
    });
    row.classList.add("hl");
    timer.current = setTimeout(() => row.classList.remove("hl"), HIGHLIGHT_MS);
  }, [req]);

  useEffect(
    () => () => {
      clearTimeout(timer.current);
      document.documentElement.classList.remove("dlg-open");
    },
    [],
  );

  // Backdrop click: the click lands on the <dialog> itself, not on its content, and the press
  // must have started there too (a text drag that ends on the backdrop must not close it).
  useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    let downOnDialog = false;
    const onDown = (e: MouseEvent) => {
      downOnDialog = e.target === dlg;
    };
    const onClick = (e: MouseEvent) => {
      const close = e.target === dlg && downOnDialog;
      downOnDialog = false;
      if (close) dlg.close();
    };
    dlg.addEventListener("mousedown", onDown);
    dlg.addEventListener("click", onClick);
    return () => {
      dlg.removeEventListener("mousedown", onDown);
      dlg.removeEventListener("click", onClick);
    };
  }, []);

  const onClose = () => {
    clearTimeout(timer.current);
    document.documentElement.classList.remove("dlg-open");
    opener.current?.focus?.();
    opener.current = null;
  };

  const api = useMemo(() => ({ open }), [open]);

  return (
    <CodedDialogContext.Provider value={api}>
      {children}
      <dialog
        ref={dialogRef}
        id="transcript-dialog"
        className="coded-dialog m-auto h-[88vh] max-h-none w-[min(1100px,calc(100vw-3rem))] max-w-none overflow-hidden rounded-[10px] border border-border bg-background p-0 text-foreground open:flex open:flex-col max-[640px]:m-0 max-[640px]:h-dvh max-[640px]:w-screen max-[640px]:rounded-none max-[640px]:border-0"
        aria-labelledby="dlg-title"
        onClose={onClose}
      >
        <div className="flex min-h-0 w-full flex-1 flex-col tabular-nums">
          <div className="flex flex-none items-start justify-between gap-4 border-b border-border bg-background px-5 py-3.5 max-[640px]:px-4 max-[640px]:py-3">
            <div>
              <h2 id="dlg-title" className="m-0 text-lg font-semibold">
                Coded transcript
              </h2>
              {turns.status === "ready" ? (
                <p className="mt-0.5 text-[0.8125rem] text-muted-foreground">
                  {rows.length} utterances, {practitioner} from the
                  practitioner. Each code shows the reason it was given.
                </p>
              ) : null}
            </div>
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="border text-2xl leading-none"
              aria-label="Close"
              onClick={() => dialogRef.current?.close()}
            >
              ×
            </Button>
          </div>
          <div
            className="min-h-0 flex-1 overflow-auto px-5 pb-5 pt-4 max-[640px]:px-4 max-[640px]:pb-4 max-[640px]:pt-3 [&_[data-slot=table-container]]:overflow-visible"
            ref={bodyRef}
          >
            {turns.status === "loading" ? (
              <p className={NOTE}>Loading transcript…</p>
            ) : null}
            {turns.status === "error" ? (
              <p className={NOTE}>
                We couldn't load the transcript.{" "}
                {turns.retry ? (
                  <Button
                    type="button"
                    variant="link"
                    className={`${LINK_BTN} inline h-auto min-h-0 py-0 align-baseline`}
                    onClick={turns.retry}
                  >
                    Try again
                  </Button>
                ) : null}
              </p>
            ) : null}
            {turns.status === "ready" ? (
              <div className="grid gap-4">
                <p className={NOTE}>
                  Each practitioner utterance carries its code and the reason
                  for it. Client utterances are not coded.
                </p>
                <details data-legend="">
                  <summary className="mb-2.5 cursor-pointer text-sm font-semibold">Code legend</summary>
                  <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-x-5 gap-y-1.5 p-0 text-[0.8125rem] text-muted-foreground">
                    {legendIds.map((id) => (
                      <li key={id} className="flex items-baseline gap-2">
                        <CodeChip id={id} />
                        <b className="font-medium text-foreground">{CODE_META[id]?.label ?? id}</b>
                      </li>
                    ))}
                    <li className="flex items-baseline gap-2">
                      <Badge variant="outline" data-code="" className={`rounded font-mono text-xs font-semibold ${PLAIN_CODE}`}>
                        P / C
                      </Badge>
                      <b className="font-medium text-foreground">P = practitioner, C = client</b>
                    </li>
                    {showNotCodedLegend ? (
                      <li className="flex items-baseline gap-2">
                        <Badge variant="outline" data-code="" className={`rounded font-mono text-xs font-semibold ${PLAIN_CODE} text-muted-foreground`}>
                          Not coded
                        </Badge>
                        <b className="font-medium text-foreground">Not coded</b>
                      </li>
                    ) : null}
                  </ul>
                </details>
                <div className="rounded-md border border-border">
                  <Table className="max-[640px]:block">
                    <TableHeader className="max-[640px]:sr-only">
                      <TableRow className="hover:bg-transparent">
                        {["Utt #", "Speaker", "Utterance", "Code(s)", "Why"].map((h) => (
                          <TableHead key={h} className={`${TH} sticky top-0 z-10 bg-muted shadow-[inset_0_-1px_0_var(--border)]`}>
                            {h}
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody className="max-[640px]:block">
                      {rows.map((r) => (
                        <TableRow key={r.turn_id} id={`utt-${r.n}`} className="max-[640px]:block max-[640px]:px-3 max-[640px]:py-2">
                          <TableCell className={STACK_CELL} data-label="Utt #">{r.n}</TableCell>
                          <TableCell className={STACK_CELL} data-label="Speaker">{r.speaker}</TableCell>
                          <TableCell className={STACK_CELL} data-label="Utterance">{r.text}</TableCell>
                          <TableCell className={STACK_CELL} data-label="Code(s)">
                            {r.codes.length > 0 ? (
                              <div data-codes="" className="flex flex-wrap gap-1">
                                {r.codes.map((c, i) => (
                                  <CodeChip
                                    key={`${c.item_id}-${i}`}
                                    id={c.item_id}
                                  />
                                ))}
                              </div>
                            ) : r.notCoded ? (
                              <Badge variant="outline" data-code="" className={`rounded font-mono text-xs font-semibold ${PLAIN_CODE} text-muted-foreground`}>
                                Not coded
                              </Badge>
                            ) : r.uncoded ? (
                              "—"
                            ) : null}
                          </TableCell>
                          <TableCell className={STACK_CELL} data-label="Why">
                            {r.why.map((w, i) => (
                              <div key={i}>
                                {r.codes.length > 1
                                  ? `${SHORT[r.codes[i]?.item_id] ?? r.codes[i]?.item_id}: ${w}`
                                  : w}
                              </div>
                            ))}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </dialog>
    </CodedDialogContext.Provider>
  );
}
