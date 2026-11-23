/**
 * Coded transcript dialog (SP2): a native modal <dialog> with the Utt # | Speaker | Utterance |
 * Code(s) | Why table. `CodedTranscriptProvider` owns the dialog and exposes `open(n?)` through
 * context, so ReportView's button and every UtteranceLink open the real thing.
 */
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Report } from "../../api/report";
import { buildCodedRows, CODE_META } from "./codedRows";
import { CodedDialogContext } from "./codedDialogContext";
import { CodeChip, SHORT } from "./ReportView";
import type { TurnsState } from "./ReportView";

export interface CodedTranscriptProviderProps {
  report: Report;
  turns: TurnsState;
  /** Practitioner turn ids shown as "Not coded" (sample only). */
  notCoded?: ReadonlySet<string>;
  children: ReactNode;
}

const HIGHLIGHT_MS = 1500;
const prefersReducedMotion = () =>
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function CodedTranscriptProvider({
  report,
  turns,
  notCoded,
  children,
}: CodedTranscriptProviderProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [req, setReq] = useState<{ id: number; n?: number } | null>(null);
  const counter = useRef(0);

  const rows = useMemo(
    () =>
      turns.status === "ready"
        ? buildCodedRows(turns.turns, report, { notCoded })
        : [],
    [turns, report, notCoded],
  );
  const practitioner = rows.filter(
    (x) => x.speaker === "P" || x.codes.length > 0 || x.uncoded,
  ).length;
  const legendIds = useMemo(() => {
    const ids: string[] = [];
    for (const b of report.behaviours ?? [])
      if (!ids.includes(b.item_id)) ids.push(b.item_id);
    return ids;
  }, [report]);

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

  // Backdrop click: the click lands on the <dialog> itself, not on its content.
  useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    const onClick = (e: MouseEvent) => {
      if (e.target === dlg) dlg.close();
    };
    dlg.addEventListener("click", onClick);
    return () => dlg.removeEventListener("click", onClick);
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
                  <button type="button" className="uref" onClick={turns.retry}>
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
                    {notCoded && notCoded.size > 0 ? (
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
