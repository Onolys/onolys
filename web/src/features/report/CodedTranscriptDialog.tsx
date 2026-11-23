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
import { CodeChip } from "./CodeChip";
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
        className="coded-dialog"
        aria-labelledby="dlg-title"
        onClose={onClose}
      >
        <div className="report-view dlg-rv">
          <div className="dlg-head">
            <div className="dlg-titles">
              <h2 id="dlg-title">Coded transcript</h2>
              {turns.status === "ready" ? (
                <p className="dlg-count">
                  {rows.length} utterances, {practitioner} from the
                  practitioner. Each code shows the reason it was given.
                </p>
              ) : null}
            </div>
            <button
              type="button"
              className="dlg-close"
              aria-label="Close"
              onClick={() => dialogRef.current?.close()}
            >
              ×
            </button>
          </div>
          <div className="dlg-body" ref={bodyRef}>
            {turns.status === "loading" ? (
              <p className="lead">Loading transcript…</p>
            ) : null}
            {turns.status === "error" ? (
              <p className="lead">
                We couldn't load the transcript.{" "}
                {turns.retry ? (
                  <button type="button" className="link-button" onClick={turns.retry}>
                    Try again
                  </button>
                ) : null}
              </p>
            ) : null}
            {turns.status === "ready" ? (
              <>
                <p className="lead">
                  Each practitioner utterance carries its code and the reason
                  for it. Client utterances are not coded.
                </p>
                <details className="dlg-legend">
                  <summary>Code legend</summary>
                  <ul className="legend">
                    {legendIds.map((id) => (
                      <li key={id}>
                        <CodeChip id={id} />
                        <b>{CODE_META[id]?.label ?? id}</b>
                      </li>
                    ))}
                    <li>
                      <span className="code c-plain">P / C</span>
                      <b>P = practitioner, C = client</b>
                    </li>
                    {showNotCodedLegend ? (
                      <li>
                        <span className="code c-plain c-dim">Not coded</span>
                        <b>Not coded</b>
                      </li>
                    ) : null}
                  </ul>
                </details>
                <div className="tbl tr">
                  <table>
                    <thead>
                      <tr>
                        <th>Utt #</th>
                        <th>Speaker</th>
                        <th>Utterance</th>
                        <th>Code(s)</th>
                        <th>Why</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.turn_id} id={`utt-${r.n}`}>
                          <td>{r.n}</td>
                          <td>{r.speaker}</td>
                          <td>{r.text}</td>
                          <td>
                            {r.codes.length > 0 ? (
                              <div className="codes">
                                {r.codes.map((c, i) => (
                                  <CodeChip
                                    key={`${c.item_id}-${i}`}
                                    id={c.item_id}
                                  />
                                ))}
                              </div>
                            ) : r.notCoded ? (
                              <span className="code c-plain c-dim">
                                Not coded
                              </span>
                            ) : r.uncoded ? (
                              "—"
                            ) : null}
                          </td>
                          <td>
                            {r.why.map((w, i) => (
                              <div key={i}>
                                {r.codes.length > 1
                                  ? `${SHORT[r.codes[i]?.item_id] ?? r.codes[i]?.item_id}: ${w}`
                                  : w}
                              </div>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}
          </div>
        </div>
      </dialog>
    </CodedDialogContext.Provider>
  );
}
