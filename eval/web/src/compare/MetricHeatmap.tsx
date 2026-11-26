import type { MouseEvent } from 'react';
import type { CompareOverview } from './compareApi';
import type { ComboLegendEntry } from './compareTypes';
import { buildCompareUrl, type CompareUrlState } from './compareUrl';
import { EvalLink, type CompareNavigate } from './CompareLink';
import { failedCombos } from './failedCombos';
import { Chip } from '../ui/Chip';
import { DataTable, type Column } from '../ui/DataTable';
import { Disclosure } from '../ui/Disclosure';
import { Note } from '../ui/Note';
import './metricHeatmap.css';

type Kind = CompareOverview['heatmap']['rows'][number]['kind'];
const labels: Record<string, string> = { reflection_question_ratio: 'R:Q', pct_cr: '%CR' };
const GROUPS: { id: string; title: string; kinds: Kind[] }[] = [
 { id: 'counts', title: 'Behavior counts', kinds: ['count', 'total'] },
 { id: 'globals', title: 'Globals', kinds: ['global'] },
 { id: 'ratios', title: 'Ratios', kinds: ['ratio'] },
];
const num = (v: number | null) => v === null ? 'n/a' : String(Math.round(v * 100) / 100);
const signed = (v: number) => v >= 0 ? `+${Math.round(v * 100) / 100}` : String(Math.round(v * 100) / 100);
const SKIPPED = 'skipped: provider unavailable';

/** Metric heatmap: rows grouped counts/globals/ratios; big number = average miss, small = signed bias. Cell flags come from the payload. */
export function MetricHeatmap({ data, legend, state, navigate, runId }: { data: CompareOverview; legend: ComboLegendEntry[]; state: CompareUrlState; navigate: CompareNavigate; runId: string }) {
 const failed = new Map(failedCombos(data).filter(f => f.all).map(f => [f.combo_key, f]));
 const skipped = (key: string) => data.leaderboard.find(row => row.combo_key === key)?.na?.reason === SKIPPED;
 const drill = (combo: string, metric?: string): CompareUrlState => ({ ...state, run: runId, view: 'compare', tab: 'deep', combos: [combo], combo, metric, code: undefined, session: undefined, turn: undefined, only: undefined });
 const activate = (event: MouseEvent<HTMLAnchorElement>, next: CompareUrlState) => {
  if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) { event.preventDefault(); navigate(next); }
 };
 const rows = data.heatmap.rows, name = (id: string) => labels[id] ?? id;
 const dataColumns: Column<(typeof rows)[number]>[] = [
  { key: 'metric', header: 'Metric', value: r => name(r.id) },
  { key: 'human', header: 'Human', value: r => data.heatmap.human[r.id].values.map(v => `${v.session_id}: ${v.value}`).join(', ') || 'n/a', sortable: false },
  ...legend.map((entry): Column<(typeof rows)[number]> => ({ key: entry.combo.combo_key, header: entry.letter, value: r => { const c = data.heatmap.cells[r.id][entry.combo.combo_key]; return c.na ? null : c.off; } })),
 ];
 return <div className="overview-heatmap-block">
  <table className="overview-heatmap" aria-label="Metric heatmap">
   <thead><tr><th className="overview-row-label" scope="col">Metric</th><th scope="col">Human</th>
    {legend.map(entry => {
     const key = entry.combo.combo_key, fail = failed.get(key);
     return <th scope="col" key={key} className={fail ? 'is-failed' : undefined}><EvalLink state={drill(key)} navigate={navigate}>{entry.letter}</EvalLink>
      {fail && <small>failed</small>}{!fail && skipped(key) && <small>skipped</small>}</th>;
    })}</tr></thead>
   <tbody>{GROUPS.map(group => {
    const groupRows = rows.filter(r => group.kinds.includes(r.kind));
    if (!groupRows.length) return null;
    return [<tr key={group.id} className="overview-group"><th scope="rowgroup" colSpan={legend.length + 2}>{group.title}</th></tr>,
     ...groupRows.map(row => {
      const label = name(row.id), humanCell = data.heatmap.human[row.id];
      return <tr key={row.id}>
       <th className="overview-row-label" scope="row">{label}</th>
       <td className="overview-human">{humanCell.values.length ? humanCell.values.map(v => <span key={v.session_id}>{v.session_id}: {v.value}</span>) : <span>n/a</span>}<small>n={humanCell.n}</small></td>
       {legend.map(entry => {
        const key = entry.combo.combo_key, cell = data.heatmap.cells[row.id][key], bad = failed.has(key);
        const best = cell.best && !skipped(key) && !bad && !cell.na, within = cell.within_tolerance === true && row.kind !== 'ratio' && !cell.na && !bad;
        const next = drill(key, row.id);
        return <td key={key} className={`overview-heatmap-cell${within ? ' within-tolerance' : ''}${best ? ' is-best' : ''}${bad ? ' is-failed' : ''}`}>
         <a href={buildCompareUrl(next)} onClick={event => activate(event, next)} aria-label={`${label}, ${entry.letter}: open Deep dive`}>
          {cell.na ? <><strong>n/a</strong><small>{cell.na.reason}</small></> : <><strong>{num(cell.off)}</strong>{cell.bias !== null && <small>{signed(cell.bias)}</small>}</>}
          <small>n={cell.n}</small>{best && <small className="overview-best">★ best</small>}
         </a>
        </td>;
       })}
      </tr>;
     })];
   })}</tbody>
  </table>
  <ul className="overview-legend" aria-label="Heatmap legend">
   <li>Big number: average miss vs human</li><li>Small: signed bias (+ over-counts, − under-counts)</li>
   <li><span className="overview-swatch within-tolerance"/>within tolerance (0.6 lines / 0.4 points)</li>
   <li><span className="overview-swatch is-best"/>best in row</li><li>R:Q and %CR: no tolerance set</li><li>n = paired sessions</li>
  </ul>
  <Disclosure label="Show data">
   <DataTable rows={rows} columns={dataColumns} rowKey={r => r.id} searchLabel="Search metrics" ariaLabel="Metric heatmap data" />
  </Disclosure>
  <Note>Human shows raw values by session. Each combo cell shows average miss and signed bias; select a cell to inspect that metric in Deep dive.</Note>
  {failed.size > 0 && <Chip tone="danger">Failed combos are excluded from best</Chip>}
 </div>;
}
