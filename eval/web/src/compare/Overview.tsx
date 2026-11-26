import type { MouseEvent } from 'react';
import type { CompareOverview } from './compareApi';
import type { CompareTabProps } from './compareTypes';
import { buildCompareUrl, type CompareUrlState } from './compareUrl';
import { EvalLink } from './CompareLink';
import { Leaderboard } from './Leaderboard';
import { failedCombos } from './failedCombos';
import { Chip } from '../ui/Chip';
import { Note } from '../ui/Note';
import './overview.css';

const labels:Record<string,string> = {reflection_question_ratio:'R:Q',pct_cr:'%CR'};
const number = (value:number|null) => value === null ? 'n/a' : String(value);
const signed = (value:number) => value >= 0 ? `+${value}` : String(value);
function Best({show}:{show:boolean}) { return show ? <span className="overview-best">★ best</span> : null; }
const skippedReason='skipped: provider unavailable';

function Verdict({data,legend,human}:{data:CompareOverview;legend:CompareTabProps<CompareOverview>['legend'];human:boolean}) {
 const failed=failedCombos(data).filter(item=>item.all);
 const letter=(key:string)=>legend.find(item=>item.combo.combo_key===key)?.letter??key;
 return <div className="overview-verdict-block">
  {human ? data.verdict.map((clause,index)=><p key={index} className="overview-verdict"><span>{clause.text}</span>{clause.claims.map((claim,i)=><small className="overview-claim" key={i} title={`${claim.metric}: ${claim.combo}`}>n={claim.n}</small>)}</p>)
   : <div className="overview-empty"><Chip tone="info">No human reference in this run</Chip><span>Only failures, cost and time are compared.</span></div>}
  {failed.length>0&&<Note>Excluded from best: {failed.map(item=>`${letter(item.combo_key)} (all runs failed: ${item.code})`).join(', ')}.</Note>}
 </div>;
}

/** Overview displays the saved projection. Only leaderboard ordering happens here. */
export function Overview({data,state,navigate,legend,runId}:CompareTabProps<CompareOverview>) {
 const human = data.has_human && data.verdict.length > 0;
 const skipped=(key:string)=>data.leaderboard.find(row=>row.combo_key===key)?.na?.reason===skippedReason;
 const drill=(combo:string,metric?:string):CompareUrlState=>({...state,run:runId,view:'compare',tab:'deep',combos:[combo],combo,metric,code:undefined,session:undefined,turn:undefined,only:undefined});
 const activate=(event:MouseEvent<HTMLAnchorElement>,next:CompareUrlState)=>{
  if(event.button===0&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&!event.shiftKey){event.preventDefault();navigate(next);}
 };
 return <section className="overview-tab" aria-label="Overview results">
    <Verdict data={data} legend={legend} human={human}/>
  <Leaderboard data={data} legend={legend} state={state} navigate={navigate} runId={runId}/>
  <Note>Count error: average tallies missed per session. Globals within ±1: ratings within one point of human. Cost and Time are operational, not compared with human. Sessions have equal weight; repeats are averaged first. Time may read short for retried units.</Note>
  {human&&<section aria-labelledby="overview-heatmap-title">
   <h3 id="overview-heatmap-title">Metric heatmap</h3>
   <div className="overview-heatmap-layout">
    {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll all combo columns. */}
    <div className={`overview-scroll ${data.combos.length>8?'overview-many-combos':''}`} role="region" aria-label={data.combos.length>8?'Metric heatmap, scroll horizontally for more combos':'Metric heatmap'} tabIndex={0}>
     <table className="overview-heatmap" aria-label="Metric heatmap" aria-describedby="overview-heatmap-caption"><thead><tr><th className="overview-row-label" scope="col">Metric</th><th scope="col">Human</th>{legend.map(entry=><th scope="col" key={entry.combo.combo_key}><EvalLink state={drill(entry.combo.combo_key)} navigate={navigate}>{entry.letter}</EvalLink>{skipped(entry.combo.combo_key)&&<small>skipped</small>}</th>)}</tr></thead>
      <tbody>{data.heatmap.rows.map(row=>{const label=labels[row.id]??row.id,humanCell=data.heatmap.human[row.id];return <tr key={row.id}>
       <th className="overview-row-label" scope="row">{label}</th><td className="overview-human">{humanCell.values.length ? humanCell.values.map(value=><span key={value.session_id}>{value.session_id}: {value.value}</span>) : <span>n/a</span>}<small>n={humanCell.n}</small></td>
       {legend.map(entry=>{const cell=data.heatmap.cells[row.id][entry.combo.combo_key],isSkipped=skipped(entry.combo.combo_key),best=cell.best&&!isSkipped&&!cell.na,within=cell.within_tolerance===true&&row.kind!=='ratio'&&!cell.na;const next=drill(entry.combo.combo_key,row.id);return <td key={entry.combo.combo_key} className={`overview-heatmap-cell${within?' within-tolerance':''}${best?' is-best':''}`}>
        <a href={buildCompareUrl(next)} onClick={event=>activate(event,next)} aria-label={`${label}, ${entry.letter}: open Deep dive`}>
         {cell.na ? <><strong>n/a</strong><span>{cell.na.reason}</span></> : <><strong>{row.kind==='global'?`off ${number(cell.off)}`:number(cell.value)}</strong><small>{row.kind!=='global'&&`off ${number(cell.off)}`}{cell.bias!==null&&`${row.kind==='global'?'':' · '}${signed(cell.bias)}`}</small></>}
         <small>n={cell.n} · {cell.n} paired of {cell.of}</small>{within&&<small>✓ within tolerance</small>}<Best show={best}/>
        </a>
       </td>;})}
      </tr>;})}</tbody>
     </table>
    </div>
    <aside aria-label="Heatmap legend"><p>✓ within tolerance: 0.6 lines / 0.4 points</p><p>★ best: outlined cell</p><p>R:Q and %CR: no tolerance set for ratios</p><p>n = paired sessions</p></aside>
   </div>
   <p id="overview-heatmap-caption"><strong>How to read:</strong> Human shows raw values by session. Each combo shows its value, average miss (off), signed bias and paired sessions; global ratings show off as the headline. Select a cell to inspect that metric in Deep dive.</p>
  </section>}
 </section>;
}
