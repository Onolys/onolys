/**
 * Single-column report document (SP2): Header, At a glance, Feedback, Behaviour counts, coded
 * transcript section, Method. Shared by real and sample reports; presentational, no fetching.
 * Utterance links call `useCodedDialog().open(n)`; the dialog itself is provided by an ancestor.
 */
import type { ReactNode } from "react";
import { Fragment, useMemo } from "react";
import type { components } from "../../api/schema";
import type { Report } from "../../api/report";
import { buildCodedRows, CODE_META, evidenceUtterances } from "./codedRows";
import { useCodedDialog } from "./codedDialogContext";
import { UtteranceLink } from "./UtteranceLink";

type Turn = components["schemas"]["TranscriptTurnV1"];

export type TurnsState =
  | { status: "loading" }
  | { status: "error"; retry?: () => void }
  | { status: "ready"; turns: readonly Turn[] };

export interface ReportViewProps {
  report: Report;
  turns: TurnsState;
  /** Page title; the real page uses "Report", the sample "Sample report". */
  title?: string;
  /** Extra header content (version select / notices, or the sample's grey line). */
  headerSlot?: ReactNode;
  /** Practitioner turn ids shown as "Not coded" (sample only). */
  notCoded?: ReadonlySet<string>;
}

export const SHORT: Record<string, string> = {
  gi: "GI", persuade: "Persuade", persuade_permission: "PwP", question: "Q", sr: "SR", cr: "CR",
  affirm: "AF", seek_collab: "Seek", emphasize_autonomy: "EA", confront: "Confront",
};
const GROUP_CLASS: Record<string, string> = {
  "Information & persuasion": "c-info",
  "Questions & reflections": "c-qr",
  "MI-adherent": "c-mia",
  "MI non-adherent": "c-mina",
};
const GLOBAL_LABEL: Record<string, string> = {
  cct: "Cultivating Change Talk", sst: "Softening Sustain Talk", partnership: "Partnership", empathy: "Empathy",
};
const FORMULA: Record<string, string> = {
  technical: "(CCT + SST) / 2",
  relational: "(PAR + EMP) / 2",
  pct_cr: "CR / (SR + CR)",
  reflection_question_ratio: "(SR + CR) / Q",
  total_mia: "Seek + AF + EA",
  total_mina: "Confront + Persuade",
};
const STATUS: Record<string, { text: string; cls: string }> = {
  below_fair: { text: "Below fair", cls: "s-low" },
  fair: { text: "Fair", cls: "s-fair" },
  good: { text: "Good", cls: "s-good" },
};
const WARNING_TEXT: Record<string, string> = {
  fewer_tips: "We could only find a few tips this time.",
  tips_failed: "We couldn't write tips this time.",
};
const GROUPS: { title: string; ids: string[]; total?: { label: string; ids: string[] } }[] = [
  { title: "Information & persuasion", ids: ["gi", "persuade", "persuade_permission"] },
  { title: "Questions & reflections", ids: ["question", "sr", "cr"] },
  {
    title: "MI-adherent",
    ids: ["affirm", "seek_collab", "emphasize_autonomy"],
    total: { label: "Total MI-adherent", ids: ["affirm", "seek_collab", "emphasize_autonomy"] },
  },
  {
    title: "MI non-adherent",
    ids: ["confront"],
    total: { label: "Total MI non-adherent (Confront + Persuade)", ids: ["confront", "persuade"] },
  },
];

export function CodeChip({ id }: { id: string }) {
  const meta = CODE_META[id];
  return <span className={`code ${GROUP_CLASS[meta?.group ?? ""] ?? "c-info"}`}>{SHORT[id] ?? id}</span>;
}

const fmtDate = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
};
const mmss = (ms: number) => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;

function spanText(r: Report, n: number | null): string {
  const s = r.header.coded_span;
  if (s?.start_turn != null && s.end_turn != null) return `Utterances ${s.start_turn + 1} to ${s.end_turn}`;
  if (s?.start_ms != null && s.end_ms != null) return `${mmss(s.start_ms)} to ${mmss(s.end_ms)}`;
  return n === null ? "Full conversation" : `Full conversation (${n} utterances)`;
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`}>{title}</h2>
      {children}
    </section>
  );
}

const valueText = (id: string, v: number | null | undefined) => {
  if (v === null || v === undefined) return "–";
  if (id === "pct_cr") return `${Math.round(v * 100)}%`;
  if (id.startsWith("total_")) return String(Math.round(v));
  return v.toFixed(1);
};

function Glance({ r, turns }: { r: Report; turns: readonly Turn[] | null }) {
  const labels = new Map((r.scorecard ?? []).map((s) => [s.item_id, s.label]));
  return (
    <Section id="glance" title="At a glance">
      <ul className="globals">
        {(r.globals ?? []).map((g) => {
          const score = g.onolys?.score ?? null;
          const ev = turns ? evidenceUtterances(g, turns) : [];
          return (
            <li key={g.item_id} className="global">
              <span className="g-name">{labels.get(g.item_id) ?? GLOBAL_LABEL[g.item_id] ?? g.item_id}</span>
              <span className="scale" role="img" aria-label={score === null ? "No score" : `${score} out of 5`}>
                {[1, 2, 3, 4, 5].map((i) => (
                  <i key={i} className={score !== null && i <= score ? "on" : undefined} />
                ))}
                <span className="sc">
                  {score ?? "–"} <small>/ 5</small>
                </span>
              </span>
              <span className="g-why">
                {g.onolys?.reason}
                {ev.length > 0 ? (
                  <span className="g-evidence">
                    Evidence: utterances{" "}
                    {ev.map((n, i) => (
                      <Fragment key={n}>
                        {i > 0 ? ", " : null}
                        <UtteranceLink n={n} />
                      </Fragment>
                    ))}
                  </span>
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>
      <div className="tbl">
        <table aria-label="Summary scores">
          <thead>
            <tr>
              <th>Summary score</th>
              <th className="num">Value</th>
              <th className="num">Fair</th>
              <th className="num">Good</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {(r.summaries ?? []).map((s) => {
              const ref = s.reference;
              const st = ref ? STATUS[s.onolys.label ?? ""] : undefined;
              return (
                <tr key={s.id}>
                  <td>
                    {s.label}
                    {FORMULA[s.id] ? <> <span className="cite">{FORMULA[s.id]}</span></> : null}
                  </td>
                  <td className="num">{valueText(s.id, s.onolys.value)}</td>
                  <td className="num">{ref ? valueText(s.id, ref.fair) : "–"}</td>
                  <td className="num">{ref ? valueText(s.id, ref.good) : "–"}</td>
                  <td>
                    {!ref ? <span className="s-none">No reference level</span> : st ? <span className={`chip ${st.cls}`}>{st.text}</span> : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="pc-note">Fair and good are reference levels, not pass marks.</p>
    </Section>
  );
}

function Feedback({ r, turns }: { r: Report; turns: readonly Turn[] | null }) {
  const tips = [...(r.tips ?? [])].sort((a, b) => a.rank - b.rank);
  const notices = (r.warnings ?? []).filter((w) => WARNING_TEXT[w.code]);
  if (tips.length === 0 && notices.length === 0) return null;
  const index = new Map((turns ?? []).map((t, i) => [t.id, i + 1]));
  return (
    <Section id="feedback" title="Feedback: ideas to try">
      {tips.length > 0 ? <p className="lead">Listed in order of priority. Start with the first.</p> : null}
      {tips.length > 0 ? (
        <ol className="tips">
          {tips.map((t) => {
            const n = index.get(t.quote.turn_id);
            return (
              <li key={t.rank} className="tip">
                <span className="rank">{t.rank}</span>
                <div className="tip-title">
                  {t.observation} <CodeChip id={t.item_id} />
                </div>
                <div className="parts">
                  <div>
                    <span className="lbl">What was said</span>
                    <blockquote className="said">
                      “{t.quote.text}”
                      {n !== undefined ? (
                        <cite>
                          Utterance <UtteranceLink n={n} />
                        </cite>
                      ) : null}
                    </blockquote>
                  </div>
                  <div className="try">
                    <span className="lbl">Try instead</span>
                    <p className="eg">{t.alternative}</p>
                  </div>
                  <div>
                    <span className="lbl">Why it matters</span>
                    <p className="why">{t.why_it_matters}</p>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      ) : null}
      {notices.map((w, i) => (
        <p key={i} className="quiet-notice" role="note">
          {WARNING_TEXT[w.code]}
        </p>
      ))}
    </Section>
  );
}

function Counts({ r }: { r: Report }) {
  const counts = new Map((r.behaviours ?? []).map((b) => [b.item_id, Math.round(b.onolys_count?.mean ?? b.onolys_count?.values?.[0] ?? 0)]));
  const sum = (ids: string[]) => ids.reduce((a, id) => a + (counts.get(id) ?? 0), 0);
  return (
    <Section id="counts" title="Behaviour counts">
      <div className="tbl">
        <table aria-label="Behaviour counts">
          <thead>
            <tr>
              <th>Code</th>
              <th>Behaviour</th>
              <th className="num">Count</th>
            </tr>
          </thead>
          <tbody>
            {GROUPS.map((g) => (
              <Fragment key={g.title}>
                <tr className="subhead">
                  <td colSpan={3}>{g.title}</td>
                </tr>
                {g.ids.map((id) => (
                  <tr key={id}>
                    <td>
                      <CodeChip id={id} />
                    </td>
                    <td>{CODE_META[id]?.label ?? id}</td>
                    <td className="num">{counts.get(id) ?? 0}</td>
                  </tr>
                ))}
                {g.total ? (
                  <tr className="total">
                    <td />
                    <td>{g.total.label}</td>
                    <td className="num">{sum(g.total.ids)}</td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function TranscriptSection({ r, turns, notCoded }: { r: Report; turns: TurnsState; notCoded?: ReadonlySet<string> }) {
  const { open } = useCodedDialog();
  const rows = useMemo(
    () => (turns.status === "ready" ? buildCodedRows(turns.turns, r, { notCoded }) : []),
    [turns, r, notCoded],
  );
  const practitioner = rows.filter((x) => x.speaker === "P" || x.codes.length > 0 || x.uncoded).length;
  return (
    <Section id="transcript" title="Coded transcript">
      {turns.status === "ready" ? (
        <p className="lead">
          {rows.length} utterances, {practitioner} from the practitioner. Each code shows the reason it was given.
        </p>
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
      <button type="button" className="btn-primary" disabled={turns.status === "loading"} onClick={() => open()}>
        {turns.status === "loading" ? "Loading transcript…" : "Open coded transcript"}
      </button>
    </Section>
  );
}

function Method({ r }: { r: Report }) {
  const m = r.method;
  if (!m) return null;
  return (
    <Section id="method" title="Method & limits">
      <p>{m.statement}</p>
      {m.limits?.map((l) => (
        <p key={l}>{l}</p>
      ))}
      {m.citation ? <p className="cite">{m.citation}</p> : null}
      {m.not_official_miti_coding ? <p className="warn">Not official MITI coding and cannot be submitted as one.</p> : null}
    </Section>
  );
}

export function ReportView({ report: r, turns, title = "Report", headerSlot, notCoded }: ReportViewProps) {
  const list = turns.status === "ready" ? turns.turns : null;
  return (
    <div className="report-view">
      <header>
        <h1>{title}</h1>
        {headerSlot}
        {r.header.change_goal ? (
          <p className="goal">
            <b>Change goal:</b> {r.header.change_goal}
          </p>
        ) : null}
        <ul className="meta">
          <li>
            <b>Protocol</b> {r.header.protocol.label}
          </li>
          <li>
            <b>Coded span</b> {spanText(r, list ? list.length : null)}
          </li>
          <li>
            <b>Date</b> {fmtDate(r.created_at)}
          </li>
        </ul>
      </header>
      <Glance r={r} turns={list} />
      <Feedback r={r} turns={list} />
      <Counts r={r} />
      <TranscriptSection r={r} turns={turns} notCoded={notCoded} />
      <Method r={r} />
    </div>
  );
}
