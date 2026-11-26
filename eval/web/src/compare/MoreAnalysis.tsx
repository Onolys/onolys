import { useState, type ReactNode } from 'react';
import { ChartFrame } from './ChartFrame';
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
// These scales place server values on the canvas; no comparison metric is calculated here.
function scales(points: {x: number; y: number}[]) {
 const maxX = Math.max(0, ...points.map(p => p.x)) || 1;
 const maxY = Math.max(0, ...points.map(p => p.y)) || 1;
 return {maxX, maxY, x: (n: number) => 70 + n / maxX * 480, y: (n: number) => 230 - n / maxY * 180};
}
function Axes({maxX, maxY, xLabel}: {maxX: number; maxY: number; xLabel: string}) {
 return <g className="more-analysis-axes">
  <path d="M70 45 V230 H550"/>
  <text x="62" y="247">0</text><text x="550" y="247" textAnchor="end">{maxX}</text>
  <text x="62" y="54" textAnchor="end">{maxY}</text>
  <text x="310" y="280" textAnchor="middle">{xLabel}</text>
  <text x="18" y="138" transform="rotate(-90 18 138)" textAnchor="middle">Count error</text>
 </g>;
}

export function MoreAnalysis({data, overview, legend, runId, navigate}: CompareTabProps<CompareAnalysis>) {
 const [lengthAxis, setLengthAxis] = useState<'turns' | 'words'>('turns');
 const letter = (key: string) => legend.find(entry => entry.combo.combo_key === key)?.letter ?? key;
 const name = (key: string) => `${letter(key)}${data.skipped_combos.includes(key) ? ' (skipped)' : ''}`;
 const lengthScale = scales(data.error_vs_length.map(point => ({x: point[lengthAxis], y: point.off})));
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
   <div role="group" aria-label="Length axis">{(['turns','words'] as const).map(axis=><button type="button" key={axis} aria-pressed={lengthAxis===axis} onClick={()=>setLengthAxis(axis)}>{axis==='turns' ? 'Turns' : 'Words'}</button>)}</div>
   <ChartFrame title="Error vs length" howToRead="Each point is one session and combo. The horizontal axis shows the chosen session length; lower points have less Count error. The data table includes each point’s n and repeat count." table={<table aria-label="Error vs length"><caption>Session and combo error by {lengthAxis}</caption><thead><tr><th scope="col">Session</th><th scope="col">Combo</th><th scope="col">{lengthAxis==='turns' ? 'Turns' : 'Words'}</th><th scope="col">Count error</th><th scope="col">n</th><th scope="col">Repeats</th></tr></thead><tbody>{data.error_vs_length.map(point=><tr key={`${point.session_id}-${point.combo_key}`}><th scope="row">{point.session_id}</th><td>{name(point.combo_key)}</td><td>{point[lengthAxis]}</td><td>{point.off}</td><td>{point.n}</td><td>{point.repeats}</td></tr>)}</tbody></table>}>
    {data.error_vs_length.length ? <svg viewBox="0 0 620 300" role="img" aria-label="Error vs length scatter"><Axes {...lengthScale} xLabel={lengthAxis==='turns' ? 'Turns' : 'Words'}/>{data.error_vs_length.map(point=><g key={`${point.session_id}-${point.combo_key}`}>
     <circle data-length-point={`${point.session_id}-${point.combo_key}`} data-x={point[lengthAxis]} cx={lengthScale.x(point[lengthAxis])} cy={lengthScale.y(point.off)} r="4"><title>{`${point.session_id}, ${name(point.combo_key)}: ${point[lengthAxis]} ${lengthAxis}, Count error ${point.off}, n=${point.n}, ${point.repeats} repeats`}</title></circle>
     <text x={lengthScale.x(point[lengthAxis])+8} y={lengthScale.y(point.off)-9}>{name(point.combo_key)} · n={point.n}</text>
    </g>)}</svg> : <p>No session length results available</p>}
   </ChartFrame>
  </>}
 </div>;
}
