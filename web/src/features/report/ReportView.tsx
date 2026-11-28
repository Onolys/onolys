/**
 * Single-column report document: Header, At a glance, Feedback, Behaviour counts, coded
 * transcript section, Method. Shared by real and sample reports; presentational, no fetching.
 * ReportView owns the coded-transcript dialog: it builds the rows once and mounts the provider, so
 * every utterance link (`useCodedDialog().open(n)`) and the "Open" button reach the same dialog.
 */
import type { ReactNode } from "react";
import { Fragment, useMemo } from "react";
import type { components } from "../../api/schema";
import type { Report } from "../../api/report";
import { buildCodedRows } from "./codedRows";
import type { CodedRow, TurnsState } from "./codedRows";
import { Button, Card, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@onolys/ui";
import { StatusChip, type ChipTone } from "../../components/StatusChip";
import { H1, LINK_BTN, NOTE } from "../../components/classes";
import { formatDate } from "../../lib/format";
import { CODE_META } from "./codeMeta";
import { CodeChip } from "./CodeChip";
import { CodedTranscriptProvider } from "./CodedTranscriptDialog";
import { useCodedDialog } from "./codedDialogContext";
import { UtteranceLink } from "./UtteranceLink";
import { GlobalComment } from "./GlobalComment";

type Turn = components["schemas"]["TranscriptTurnV1"];

export type { TurnsState };

export interface ReportViewProps {
  report: Report;
  turns: TurnsState;
  /** Page title; the real page uses "Report", the sample "Sample report". */
  title?: string;
  /** Report identifier from the API envelope (absent for the public sample). */
  reportId?: string;
  /** Page-specific actions after the report. */
  footerSlot?: ReactNode;
  /** Extra header notices, or the sample's grey line. */
  headerSlot?: ReactNode;
  /** Practitioner turn ids shown as "Not coded" (sample only). */
  notCoded?: ReadonlySet<string>;
}

const GLOBAL_LABEL: Record<string, string> = {
  cct: "Cultivating Change Talk",
  sst: "Softening Sustain Talk",
  partnership: "Partnership",
  empathy: "Empathy",
};
const FORMULA: Record<string, string> = {
  technical: "(CCT + SST) / 2",
  relational: "(PAR + EMP) / 2",
  pct_cr: "CR / (SR + CR)",
  reflection_question_ratio: "(SR + CR) / Q",
  total_mia: "Seek + AF + EA",
  total_mina: "Confront + Persuade",
};
// Reused StatusChip tones: failed = low, wait = fair, done = good (the visible text always says the status).
const STATUS: Record<string, { text: string; tone: ChipTone }> = {
  below_fair: { text: "Below fair", tone: "failed" },
  fair: { text: "Fair", tone: "wait" },
  good: { text: "Good", tone: "done" },
};
const TH = "text-xs font-semibold uppercase tracking-wider text-muted-foreground";
const TBL = "rounded-md border border-border";
const CELL = "whitespace-normal align-top";
const LABEL = "block text-[0.6875rem] font-semibold uppercase tracking-widest text-muted-foreground";
const WARNING_TEXT: Record<string, string> = {
  short_session: "This session is shorter than 10 minutes, so global ratings may be harder to judge.",
  reflection_before_client_speech: "The practitioner speaks first in this excerpt. Opening reflections have no earlier client speech here to refer to.",
  fewer_tips: "We could only find a few tips this time.",
  tips_failed: "We couldn't write tips this time.",
  // Per-run engine codes (they can repeat per item; the notes below show each message once).
  quote_not_found: "Some quotes could not be matched to the transcript, so they were left out.",
  overlap: "Some coded lines overlapped, so only one code was kept for them.",
  insufficient_evidence: "For some items there was not enough evidence in the transcript to be sure.",
  capped: "Some scores were limited because the evidence was thin.",
  reason_withheld_tone: "Some written reasons were left out because their wording was not suitable to show.",
};
const GENERIC_WARNING = "Some parts of this report had a processing note.";
/** Plain-language notes for the report's warnings: known codes by their text, unknown ones as one generic line, each message once. */
const warningNotes = (warnings: Report["warnings"]): string[] => [
  ...new Set((warnings ?? []).map((w) => WARNING_TEXT[w.code] ?? GENERIC_WARNING)),
];
const GROUPS: {
  title: string;
  ids: string[];
  total?: { label: string; ids: string[] };
}[] = [
  {
    title: "Information & persuasion",
    ids: ["gi", "persuade", "persuade_permission"],
  },
  { title: "Questions & reflections", ids: ["question", "sr", "cr"] },
  {
    title: "MI-adherent",
    ids: ["affirm", "seek_collab", "emphasize_autonomy"],
    total: {
      label: "Total MI-adherent",
      ids: ["affirm", "seek_collab", "emphasize_autonomy"],
    },
  },
  {
    title: "MI non-adherent",
    ids: ["confront"],
    total: {
      label: "Total MI non-adherent (Confront + Persuade)",
      ids: ["confront", "persuade"],
    },
  },
];

const mmss = (ms: number) =>
  `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;

function spanText(r: Report, n: number | null): string {
  const s = r.header.coded_span;
  if (s?.start_turn != null && s.end_turn != null)
    return `Utterances ${s.start_turn + 1} to ${s.end_turn}`;
  if (s?.start_ms != null && s.end_ms != null)
    return `${mmss(s.start_ms)} to ${mmss(s.end_ms)}`;
  return n === null
    ? "Full conversation"
    : `Full conversation (${n} utterances)`;
}

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="grid grid-cols-1 gap-4 border-t border-border pt-8">
      <h2 id={`${id}-h`} className="m-0 text-lg font-semibold leading-tight text-balance">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** An absent value: a dash a screen reader hears as "no data". */
const NO_DATA = (
  <span role="img" aria-label="no data">
    –
  </span>
);

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
      <ul className="m-0 grid list-none grid-cols-1 rounded-md border border-border p-0">
        {(r.globals ?? []).map((g) => {
          const score = g.onolys?.score ?? null;
          return (
            <li
              key={g.item_id}
              data-global=""
              className="grid items-center gap-x-5 gap-y-2 border-b border-border p-4 last:border-b-0 sm:grid-cols-[190px_150px_minmax(0,1fr)]"
            >
              <span className="font-semibold">
                {labels.get(g.item_id) ?? GLOBAL_LABEL[g.item_id] ?? g.item_id}
              </span>
              <span
                className="flex items-center gap-1"
                data-scale=""
                role="img"
                aria-label={score === null ? "No score" : `${score} out of 5`}
              >
                {[1, 2, 3, 4, 5].map((i) => (
                  <span
                    key={i}
                    data-segment=""
                    data-on={score !== null && i <= score ? "" : undefined}
                    className="block h-2 w-5 rounded-sm bg-muted data-[on]:bg-primary"
                  />
                ))}
                <span className="ml-2 whitespace-nowrap font-bold">
                  {score ?? "–"} <small className="text-xs font-normal text-muted-foreground">/ 5</small>
                </span>
              </span>
              <span className="min-w-0 text-sm text-muted-foreground">
                <GlobalComment global={g} turns={turns} />
              </span>
            </li>
          );
        })}
      </ul>
      <div className={TBL}>
        <Table aria-label="Summary scores">
          <TableHeader>
            <TableRow className="bg-muted hover:bg-muted">
              <TableHead className={TH}>Summary score</TableHead>
              <TableHead className={`${TH} text-right`}>Value</TableHead>
              <TableHead className={`${TH} text-right`}>Fair</TableHead>
              <TableHead className={`${TH} text-right`}>Good</TableHead>
              <TableHead className={TH}>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(r.summaries ?? []).map((s) => {
              const ref = s.reference;
              const st = ref ? STATUS[s.onolys.label ?? ""] : undefined;
              return (
                <TableRow key={s.id}>
                  <TableCell className={CELL}>
                    {s.label}
                    {FORMULA[s.id] ? (
                      <>
                        {" "}
                        <span className="text-[0.8125rem] text-muted-foreground">{FORMULA[s.id]}</span>
                      </>
                    ) : null}
                  </TableCell>
                  <TableCell className={`${CELL} text-right`}>{valueText(s.id, s.onolys.value)}</TableCell>
                  <TableCell className={`${CELL} text-right`}>
                    {ref ? valueText(s.id, ref.fair) : "–"}
                  </TableCell>
                  <TableCell className={`${CELL} text-right`}>
                    {ref ? valueText(s.id, ref.good) : "–"}
                  </TableCell>
                  <TableCell className={CELL}>
                    {!ref ? (
                      <span className="text-muted-foreground">No reference level</span>
                    ) : st ? (
                      <StatusChip tone={st.tone}>{st.text}</StatusChip>
                    ) : null}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      <p className="text-xs text-muted-foreground">
        Fair and good are reference levels, not pass marks.
      </p>
    </Section>
  );
}

function Feedback({ r, turns }: { r: Report; turns: readonly Turn[] | null }) {
  const tips = [...(r.tips ?? [])].sort((a, b) => a.rank - b.rank);
  const notices = warningNotes(r.warnings);
  if (tips.length === 0 && notices.length === 0) return null;
  const index = new Map((turns ?? []).map((t, i) => [t.id, i + 1]));
  return (
    <Section id="feedback" title="Feedback: ideas to try">
      {tips.length > 0 ? (
        <p className={NOTE}>
          Listed in order of priority. Start with the first.
        </p>
      ) : null}
      {tips.length > 0 ? (
        <ol className="m-0 grid list-none grid-cols-1 gap-5 p-0">
          {tips.map((t) => {
            const n = index.get(t.quote.turn_id);
            return (
              <li key={t.rank} data-tip="">
                <Card className="grid grid-cols-1 gap-x-4 gap-y-0 p-5 sm:grid-cols-[36px_minmax(0,1fr)]">
                <span className="mb-2 grid size-8 place-items-center rounded-full bg-primary font-bold text-primary-foreground sm:mb-0">{t.rank}</span>
                <div className="mb-4 mt-[3px] flex flex-wrap items-center gap-x-2.5 gap-y-1.5 font-semibold">
                  <h3 className="m-0 text-base font-semibold">{t.title || `${CODE_META[t.item_id]?.label ?? GLOBAL_LABEL[t.item_id] ?? "Response"}: an idea to try`}</h3> <CodeChip id={t.item_id} />
                </div>
                <div className="grid grid-cols-1 gap-4 sm:col-start-2">
                  {t.observation ? <p className={NOTE}>{t.observation}</p> : null}
                  <div className="rounded-md bg-score-low-bg px-3.5 py-3">
                    <span className={`${LABEL} mb-1 text-score-low`}>What was said</span>
                    <blockquote className="m-0 text-base font-normal text-score-low">
                      “{t.quote.text}”
                      {n !== undefined ? (
                        <cite className="ml-1.5 whitespace-nowrap text-xs not-italic text-muted-foreground">
                          Utterance <UtteranceLink n={n} />
                        </cite>
                      ) : null}
                    </blockquote>
                  </div>
                  <div data-try="" className="rounded-md bg-muted px-3.5 py-3">
                    <span className={`${LABEL} mb-1 text-primary`}>Try instead</span>
                    <p data-eg="" className="text-base font-normal text-primary">{t.alternative}</p>
                  </div>
                  <div>
                    <span className={`${LABEL} mb-1`}>Why it matters</span>
                    <p>{t.why_it_matters}</p>
                  </div>
                </div>
                </Card>
              </li>
            );
          })}
        </ol>
      ) : null}
      {notices.map((text) => (
        <p key={text} className={NOTE} role="note">
          {text}
        </p>
      ))}
    </Section>
  );
}

function Counts({ r }: { r: Report }) {
  // Keep the unrounded means: a total is round(sum of means), not the sum of the rounded rows.
  // A behaviour with no onolys_count has no data: it is left out (shown as a dash), never counted as 0.
  const means = new Map<string, number>();
  for (const b of r.behaviours ?? []) {
    const v = b.onolys_count?.mean ?? b.onolys_count?.values?.[0];
    if (typeof v === "number") means.set(b.item_id, v);
  }
  const counts = new Map([...means].map(([id, v]) => [id, Math.round(v)]));
  const sum = (ids: string[]) =>
    ids.some((id) => means.has(id))
      ? String(Math.round(ids.reduce((a, id) => a + (means.get(id) ?? 0), 0)))
      : NO_DATA;
  return (
    <Section id="counts" title="Behaviour counts">
      <div className={TBL}>
        <Table aria-label="Behaviour counts">
          <TableHeader>
            <TableRow className="bg-muted hover:bg-muted">
              <TableHead className={TH}>Code</TableHead>
              <TableHead className={TH}>Behaviour</TableHead>
              <TableHead className={`${TH} text-right`}>Count</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {GROUPS.map((g) => (
              <Fragment key={g.title}>
                <TableRow className="bg-muted hover:bg-muted">
                  <TableCell colSpan={3} className={`${TH} py-1.5`}>
                    {g.title}
                  </TableCell>
                </TableRow>
                {g.ids.map((id) => (
                  <TableRow key={id}>
                    <TableCell className={CELL}>
                      <CodeChip id={id} />
                    </TableCell>
                    <TableCell className={CELL}>{CODE_META[id]?.label ?? id}</TableCell>
                    <TableCell className={`${CELL} text-right`}>{counts.get(id) ?? NO_DATA}</TableCell>
                  </TableRow>
                ))}
                {g.total ? (
                  <TableRow className="bg-muted font-semibold">
                    <TableCell />
                    <TableCell className={CELL}>{g.total.label}</TableCell>
                    <TableCell className={`${CELL} text-right`}>{sum(g.total.ids)}</TableCell>
                  </TableRow>
                ) : null}
              </Fragment>
            ))}
          </TableBody>
        </Table>
      </div>
    </Section>
  );
}

function TranscriptSection({
  turns,
  rows,
  practitioner,
}: {
  turns: TurnsState;
  rows: readonly CodedRow[];
  practitioner: number;
}) {
  const { open } = useCodedDialog();
  return (
    <Section id="transcript" title="Coded transcript">
      {turns.status === "ready" ? (
        <p className={NOTE}>
          {rows.length} utterances, {practitioner} from the practitioner. Each
          code shows the reason it was given.
        </p>
      ) : null}
      {turns.status === "error" ? (
        <p className={NOTE}>
          We couldn't load the transcript.{" "}
          {turns.retry ? (
            <Button type="button" variant="link" className={`${LINK_BTN} inline h-auto min-h-0 py-0 align-baseline`} onClick={turns.retry}>
              Try again
            </Button>
          ) : null}
        </p>
      ) : null}
      <div>
        <Button
          type="button"
          disabled={turns.status === "loading"}
          onClick={() => open()}
        >
          {turns.status === "loading"
            ? "Loading transcript…"
            : "Open coded transcript"}
        </Button>
      </div>
    </Section>
  );
}

function Method({ r }: { r: Report }) {
  const m = r.method;
  if (!m) return null;
  return (
    <Section id="method" title="Method & limits">
      <p>Onolys reads the transcript against the MITI 4.2.1 manual. Compare this reading with your own judgment.</p>
      {r.header.coded_span ? <p>Coded span: {spanText(r, null)}.</p> : null}
      <p>Tone of voice, pauses and body language are unavailable. Automatic speaker labels and timestamps may be wrong; utterance splitting affects counts.</p>
      {m.citation ? <p className="text-[0.8125rem] text-muted-foreground">{m.citation}</p> : null}
      {m.not_official_miti_coding ? (
        <p className={NOTE}>
          Not official MITI coding and cannot be submitted as one.
        </p>
      ) : null}
    </Section>
  );
}

export function ReportView({
  report: r,
  turns,
  title = "Report",
  headerSlot,
  reportId,
  footerSlot,
  notCoded,
}: ReportViewProps) {
  const list = turns.status === "ready" ? turns.turns : null;
  const rows = useMemo(
    () =>
      turns.status === "ready"
        ? buildCodedRows(turns.turns, r, { notCoded })
        : [],
    [turns, r, notCoded],
  );
  const practitioner = useMemo(
    () =>
      rows.filter((x) => x.speaker === "P" || x.codes.length > 0 || x.uncoded)
        .length,
    [rows],
  );
  const legendIds = useMemo(
    () => [...new Set((r.behaviours ?? []).map((b) => b.item_id))],
    [r],
  );
  return (
    <CodedTranscriptProvider
      turns={turns}
      rows={rows}
      practitioner={practitioner}
      legendIds={legendIds}
      showNotCodedLegend={!!notCoded && notCoded.size > 0}
    >
      <div data-report-view="" className="mx-auto grid w-full min-w-0 grid-cols-1 gap-8 tabular-nums">
        <header className="grid grid-cols-1 gap-2">
          <h1 className={`${H1} text-balance tracking-tight`}>{title}</h1>
          {reportId ? <p className="break-all text-sm"><b>Report ID:</b> <span>{reportId}</span></p> : null}
          {r.header.change_goal ? (
            <p>
              <b>Change goal:</b> {r.header.change_goal}
            </p>
          ) : null}
          {headerSlot}
          {!reportId ? <ul className="m-0 flex list-none flex-wrap gap-x-5 gap-y-1 p-0 text-[0.8125rem] text-muted-foreground">
            <li>
              <b className="font-medium text-foreground">Protocol</b> {r.header.protocol.label}
            </li>
            <li>
              <b className="font-medium text-foreground">Coded span</b> {spanText(r, list ? list.length : null)}
            </li>
            <li>
              <b className="font-medium text-foreground">Date</b> {formatDate(r.created_at)}
            </li>
          </ul> : null}
        </header>
        <Glance r={r} turns={list} />
        <Feedback r={r} turns={list} />
        <Counts r={r} />
        <TranscriptSection
          turns={turns}
          rows={rows}
          practitioner={practitioner}
        />
        <Method r={r} />
        {footerSlot}
      </div>
    </CodedTranscriptProvider>
  );
}
