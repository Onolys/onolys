import { useEffect, useState } from 'react';
import { Button } from '@onolys/ui';
import { Chip, type ChipTone } from '../../ui/Chip';
import { ComboTag } from '../../ui/ComboTag';
import { DataTable, type Column } from '../../ui/DataTable';
import { Disclosure } from '../../ui/Disclosure';
import { Note } from '../../ui/Note';
import type { CompareLines, CompareReasoning } from '../compareApi';
import type { CompareTabProps } from '../compareTypes';
import { ErrorNotice, Snippets } from './lineShared';
import '../lineView.css';

/** Distance from the human rating: tone always travels with text (and the chip icon), never colour alone. */
export function ratingChip(value: number | undefined, human: number | undefined): { tone: ChipTone; text: string } {
 if (value === undefined || human === undefined) return { tone: 'muted', text: 'n/a' };
 const off = Math.abs(value - human);
 return off === 0 ? { tone: 'success', text: 'exact' } : off === 1 ? { tone: 'warning', text: 'off 1' } : { tone: 'danger', text: 'off 2+' };
}

function Ratings({ data, api, runId, selected, letter }: { data: CompareLines; api: CompareTabProps<CompareLines>['api']; runId: string; selected: string[]; letter: (key: string) => string }) {
 const [page, setPage] = useState<CompareReasoning>(); const [error, setError] = useState<unknown>(); const [attempt, setAttempt] = useState(0); const [cursor, setCursor] = useState<string>(); const [pending, setPending] = useState(true);
 const keys = JSON.stringify(selected);
 useEffect(() => {
  const controller = new AbortController();
  api.compareReasoning(runId, { session: data.session_id, kind: 'global', combos: JSON.parse(keys) as string[], ...(cursor ? { cursor } : {}) }, controller.signal).then(value => { if (!controller.signal.aborted) { setPage(old => cursor && old ? { ...value, groups: [...old.groups, ...value.groups] } : value); setError(undefined); setPending(false); } }).catch(reason => { if (!controller.signal.aborted) { setError(reason); setPending(false); } });
  return () => controller.abort();
 }, [api, runId, data.session_id, keys, cursor, attempt]);
 const metrics = Array.from(new Set([...Object.keys(data.globals.human), ...Object.values(data.globals.combos).flatMap(rows => rows.flatMap(row => Object.keys(row)))]));
 const columns: Column<string>[] = [
  { key: 'metric', header: 'Global', value: metric => metric },
  { key: 'human', header: 'Human', value: metric => data.globals.human[metric] ?? 'n/a' },
  ...selected.map((key, index): Column<string> => ({
   key, header: letter(key), sortable: false,
   value: metric => data.globals.combos[key]?.map(row => row[metric] ?? 'n/a').join(' / ') ?? 'n/a',
   render: metric => {
    const rows = data.globals.combos[key];
    if (!rows?.length) return 'n/a';
    return <span className="line-ratings-cell"><ComboTag index={index} letter={letter(key)} />{rows.map((row, i) => { const chip = ratingChip(row[metric], data.globals.human[metric]); return <Chip key={i} tone={chip.tone}>{row[metric] ?? 'n/a'} · {chip.text}</Chip>; })}</span>;
   },
  })),
 ];
 const withReasons = metrics.filter(metric => page?.groups.some(group => group.code === metric && group.snippets.length > 0));
 return <>
  <DataTable rows={metrics} columns={columns} rowKey={metric => metric} ariaLabel="Session global ratings" searchLabel="Search globals" empty="No global ratings saved." />
  <Note>How to read: Each chip is one repeat, shown in repeat order, with its distance from the human rating: exact, off 1, or off 2+. Reasons are saved output; evidence quotes are verified by the server.</Note>
  {pending && <p role="status">Loading global reasons…</p>}
  {error !== undefined && <ErrorNotice error={error} retry={() => { setPending(true); setAttempt(n => n + 1); }} />}
  {withReasons.length > 0 && <Disclosure label="Show reasoning">{withReasons.map(metric => <section key={metric}><h4>{metric}</h4>{selected.map(key => { const snippets = page?.groups.filter(group => group.code === metric).flatMap(group => group.snippets.filter(snippet => snippet.combo_key === key)) ?? []; return snippets.length ? <section key={key}><h5>{letter(key)} · {key}</h5><Snippets snippets={snippets} /></section> : null; })}</section>)}</Disclosure>}
  {page?.next_cursor && <Button disabled={pending} onClick={() => { setPending(true); setCursor(page.next_cursor!); }}>Load more global reasons</Button>}
 </>;
}

/** Session global ratings, collapsed by default; ratings and reasons are only requested once opened. */
export function SessionRatings(props: { data: CompareLines; api: CompareTabProps<CompareLines>['api']; runId: string; selected: string[]; letter: (key: string) => string }) {
 return <section className="line-ratings"><h3>Session globals</h3><Disclosure label="Show global ratings"><Ratings {...props} /></Disclosure></section>;
}
