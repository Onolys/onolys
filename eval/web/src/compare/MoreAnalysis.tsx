import { useState, type ReactNode } from 'react';
import { ChartFrame } from './ChartFrame';
import { EvalLink } from './CompareLink';
import type { CompareAnalysis, NA, ValueCell } from './compareApi';
import type { CompareTabProps } from './compareTypes';
import './moreAnalysis.css';

const unavailable = (na: NA | undefined) => `n/a${na ? ` - ${na.reason}` : ''}`;
const levelNames: Record<string, string> = {
 technical: 'Technical', relational: 'Relational', pct_cr: '%CR', reflection_question_ratio: 'R:Q',
};
function Value({cell}: {cell: ValueCell}) {
 return <>{cell.na || cell.value === null ? unavailable(cell.na) : `value ${cell.value}`} · n={cell.n}</>;
}
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

export function MoreAnalysis({data, legend, runId, navigate}: CompareTabProps<CompareAnalysis>) {
 const [lengthAxis, setLengthAxis] = useState<'turns' | 'words'>('turns');
 const letter = (key: string) => legend.find(entry => entry.combo.combo_key === key)?.letter ?? key;
 const name = (key: string) => `${letter(key)}${data.skipped_combos.includes(key) ? ' (skipped)' : ''}`;
 const priced = [...data.frontier.points, ...data.frontier.dominated];
 const costScale = scales(priced.map(point => ({x: point.cost_per_run_usd, y: point.count_error})));
 const lengthScale = scales(data.error_vs_length.map(point => ({x: point[lengthAxis], y: point.off})));
 const costTable = <table aria-label="Cost vs accuracy"><caption>Cost and Count error from the server</caption><thead><tr><th scope="col">Combo</th><th scope="col">Cost per run (USD)</th><th scope="col">Count error</th><th scope="col">Frontier</th></tr></thead><tbody>
  {priced.map(point => <tr key={point.combo_key}><th scope="row">{name(point.combo_key)}</th><td>{point.cost_per_run_usd} · n={point.cost_n}</td><td>{point.count_error} · n={point.n}</td><td>{data.frontier.points.some(p => p.combo_key === point.combo_key) ? 'Frontier' : 'Dominated'}</td></tr>)}
 </tbody></table>;
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
  <section aria-labelledby="more-baseline"><h3 id="more-baseline">Human-vs-human baseline</h3><p>{unavailable(data.baseline.na)}</p></section>
  <section aria-labelledby="more-reliability"><h3 id="more-reliability">Reliability</h3>
   <ScrollTable name="Reliability"><table aria-label="Reliability"><caption>Repeat consistency, failures and time from the server</caption><thead><tr><th scope="col">Combo</th><th scope="col">Same MITI level</th><th scope="col">Repeat agreement</th><th scope="col">Failures</th><th scope="col">Time</th></tr></thead><tbody>
    {data.combos.map(combo => {const row=data.reliability[combo.combo_key];return <tr key={combo.combo_key}><th scope="row">{name(combo.combo_key)}</th>{!row ? <td colSpan={4}>n/a</td> : <>
     <td>{row.na ? unavailable(row.na) : Object.entries(row.levels).map(([metric,cell]) => <div key={metric}>{levelNames[metric] ?? metric}: <Value cell={cell}/></div>)}</td>
     <td>{Object.entries(row.repeat_agreement).map(([metric,cell]) => <div key={metric}><span>{metric}: </span><span>{cell.na || cell.value === null ? `${unavailable(cell.na)} · n=${cell.n}` : `${cell.agree} of ${cell.n} agree · value ${cell.value} · n=${cell.n}`}</span></div>)}</td>
     <td>{row.failures.length ? row.failures.map(failure => <div key={failure.code}>{failure.code}: {failure.count}</div>) : 'None reported'}</td>
     <td>{row.time.mean_seconds === null ? 'n/a' : `${row.time.mean_seconds} seconds`} · n={row.time.n} · retried runs: {row.time.retried_runs}</td>
    </>}</tr>;})}
   </tbody></table></ScrollTable>
   <p><strong>How to read:</strong> Each row shows the server’s repeat consistency and operational results. Each n is the number of observations for that value; failures are listed by their saved code.</p>
  </section>
  {!data.has_human ? <p>no human reference</p> : <>
   <ChartFrame title="Cost vs accuracy" howToRead="Each letter is a priced combo: lower cost is farther left and lower Count error is nearer the bottom. The line joins only the server’s frontier combos; unpriced and unavailable combos are listed below." table={costTable}>
    {priced.length ? <svg viewBox="0 0 620 300" role="img" aria-label="Cost vs accuracy scatter"><Axes {...costScale} xLabel="Cost per run (USD)"/>
     <polyline className="more-analysis-frontier" data-frontier-combos={data.frontier.points.map(point=>point.combo_key).join(',')} points={data.frontier.points.map(point=>`${costScale.x(point.cost_per_run_usd)},${costScale.y(point.count_error)}`).join(' ')}/>
     {priced.map(point => {const frontier=data.frontier.points.some(p=>p.combo_key===point.combo_key);return <g key={point.combo_key}>
      <circle data-cost-point={point.combo_key} data-frontier={frontier} cx={costScale.x(point.cost_per_run_usd)} cy={costScale.y(point.count_error)} r={frontier ? 6 : 4}><title>{`${name(point.combo_key)}: cost ${point.cost_per_run_usd} USD, cost n=${point.cost_n}; Count error ${point.count_error}, n=${point.n}; ${frontier ? 'Frontier' : 'Dominated'}`}</title></circle>
      <text x={costScale.x(point.cost_per_run_usd)+8} y={costScale.y(point.count_error)-9}>{name(point.combo_key)}{frontier ? ' ★' : ''} · n={point.n}</text>
     </g>;})}
    </svg> : <p>No priced results available</p>}
   </ChartFrame>
   {!!data.frontier.unpriced.length && <ul aria-label="Unpriced combos">{data.frontier.unpriced.map(point=><li key={point.combo_key}>{name(point.combo_key)}: {unavailable(point.na)} · Count error {point.count_error} · n={point.n}</li>)}</ul>}
   {!!data.frontier.unavailable.length && <ul aria-label="Unavailable combos">{data.frontier.unavailable.map(point=><li key={point.combo_key}>{name(point.combo_key)}: {unavailable(point.na)} · n={point.n}</li>)}</ul>}
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
