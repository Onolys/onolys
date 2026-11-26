import type { ReactNode } from 'react';
import { ChartFrame } from './ChartFrame';
import { Disclosure } from '../ui/Disclosure';
import { ErrorVsLength } from './charts/ErrorVsLength';
import { EvalLink } from './CompareLink';
import type { CompareAnalysis, NA } from './compareApi';
import type { CompareTabProps } from './compareTypes';
import { CostAccuracyScatter } from './charts/CostAccuracyScatter';
import { BaselineCard } from './charts/BaselineCard';
import { ReliabilityTable } from './charts/ReliabilityTable';
import { failedCombos } from './failedCombos';
import './moreAnalysis.css';

const unavailable = (na: NA | undefined) => `n/a${na ? ` - ${na.reason}` : ''}`;
function ScrollTable({name, children}: {name: string; children: ReactNode}) {
 // Keyboard focus lets people scroll the wide data table without a pointer.
 // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
 return <div className="table-scroll" role="region" aria-label={`${name} table`} tabIndex={0}>{children}</div>;
}
export function MoreAnalysis({data, overview, legend, runId, navigate}: CompareTabProps<CompareAnalysis>) {
 const letter = (key: string) => legend.find(entry => entry.combo.combo_key === key)?.letter ?? key;
 const name = (key: string) => `${letter(key)}${data.skipped_combos.includes(key) ? ' (skipped)' : ''}`;
 const headToHead = () => <table aria-label="Head-to-head"><caption>Row combo compared with column combo</caption><thead><tr><th scope="col">Combo</th>{data.combos.map(combo => <th scope="col" key={combo.combo_key}>{name(combo.combo_key)}</th>)}</tr></thead><tbody>{data.combos.map(row => <tr key={row.combo_key}><th scope="row">{name(row.combo_key)}</th>{data.combos.map(col => {
  if (row.combo_key === col.combo_key) return <td key={col.combo_key}>Same combo</td>;
  const pair = data.head_to_head.find(pair => pair.a === row.combo_key && pair.b === col.combo_key || pair.b === row.combo_key && pair.a === col.combo_key);
  return <td key={col.combo_key}>{!pair ? 'n/a' : pair.na ? `${unavailable(pair.na)} · n=${pair.n}` : `${letter(row.combo_key)} closer than ${letter(col.combo_key)} on ${pair.a === row.combo_key ? pair.a_closer : pair.b_closer} of ${pair.n} sessions · ${pair.ties} ties`}</td>;
 })}</tr>)}</tbody></table>;
 const grid = (links: boolean) => <table aria-label="Interviews by combo"><caption>Session Count error, paired n, successful repeats and labeled codes</caption><thead><tr><th scope="col">Session</th>{data.combos.map(combo => <th scope="col" key={combo.combo_key}>{name(combo.combo_key)}</th>)}</tr></thead><tbody>{data.grid.map(row => <tr key={row.session_id}>
  <th scope="row">{links ? <EvalLink state={{run: runId, view: 'compare', tab: 'lines', session: row.session_id}} navigate={navigate}>{row.session_id}</EvalLink> : row.session_id}</th>
  {data.combos.map(combo => {const cell = row.cells[combo.combo_key];return <td key={combo.combo_key}>{cell ? <>{cell.na || cell.off === null ? unavailable(cell.na) : `off ${cell.off}`} · n={cell.n} · {cell.repeats} repeats · {cell.codes_labeled} codes labeled</> : 'n/a'}</td>;})}
 </tr>)}</tbody></table>;
 return <div className="more-analysis">
  <h2>More analysis</h2>
  <BaselineCard baseline={data.baseline}/>
  <ReliabilityTable data={data} legend={legend} failed={failedCombos(overview)} best={Object.fromEntries(overview.leaderboard.map(row=>[row.combo_key,{failures:row.operational_best.failures,time:row.operational_best.time}]))}/>
  {!data.has_human ? <p>no human reference</p> : <>
   <CostAccuracyScatter data={data} legend={legend} failed={failedCombos(overview)}/>
   <ChartFrame title="Head-to-head" howToRead="Read a row against a column to see how often the row combo was closer to the human counts. Ties and the paired session count come from the server." table={headToHead()}>
    <ScrollTable name="Head-to-head">{headToHead()}</ScrollTable>
   </ChartFrame>
   <ChartFrame title="Interviews by combo" howToRead="Each cell is that session’s Count error, with its paired n and repeat count. Open a session link to inspect its transcript in Line view." table={grid(false)}>
    {data.grid.length ? <ScrollTable name="Interviews by combo">{grid(true)}</ScrollTable> : <p>No session results available</p>}
   </ChartFrame>
   <Disclosure label="Show error vs interview length"><ErrorVsLength data={data} legend={legend} failed={failedCombos(overview)}/></Disclosure>
  </>}
 </div>;
}
