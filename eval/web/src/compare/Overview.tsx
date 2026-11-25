import { useState, type MouseEvent } from 'react';
import type { CompareCell, CompareOverview, QualityCell } from './compareApi';
import type { CompareTabProps } from './compareTypes';
import { buildCompareUrl, type CompareUrlState } from './compareUrl';
import { EvalLink } from './CompareLink';
import './overview.css';

type Leader = CompareOverview['leaderboard'][number];
type Column = 'count' | 'globals_within_1' | 'line_accuracy' | 'macro_f1' | 'fails' | 'cost' | 'time';
const columns: {key:Column;label:string;descending?:boolean}[] = [
 {key:'count',label:'Count error'}, {key:'globals_within_1',label:'Globals within ±1',descending:true},
 {key:'line_accuracy',label:'Line match accuracy',descending:true}, {key:'macro_f1',label:'Line match macro F1',descending:true},
 {key:'fails',label:'Fails'}, {key:'cost',label:'Cost'}, {key:'time',label:'Time'},
];
const labels:Record<string,string> = {reflection_question_ratio:'R:Q',pct_cr:'%CR'};
const number = (value:number|null) => value === null ? 'n/a' : String(value);
const signed = (value:number) => value >= 0 ? `+${value}` : String(value);
const failureCount = (row:Leader) => row.failures.reduce((n,failure)=>n+failure.count,0);
function sortValue(row:Leader,key:Column):number|null {
 switch(key) {
  case 'count': return row.na ? null : row.off;
  case 'fails': return failureCount(row);
  case 'cost': return row.cost.na ? null : row.cost.per_run_usd;
  case 'time': return row.time.mean_seconds;
  default: return row[key].na ? null : row[key].value;
 }
}
function Best({show}:{show:boolean}) { return show ? <span className="overview-best">★ best</span> : null; }
function Score({cell,of,skipped,count=false}:{cell:CompareCell|QualityCell;of:number;skipped:boolean;count?:boolean}) {
 const value=count ? (cell as CompareCell).off : cell.value;
 return <>{cell.na ? <span>n/a — {cell.na.reason}</span> : <span>{number(value)}</span>}<small>{cell.n} paired of {of}</small><Best show={!skipped && !cell.na && cell.best}/></>;
}

function LeaderScore({row,column,skipped,sessions}:{row:Leader;column:Column;skipped:boolean;sessions:number}) {
 switch(column) {
  case 'count': return <Score cell={row} of={row.of} skipped={skipped} count/>;
  case 'fails': return <>
   {row.failures.length ? row.failures.map(failure=><span key={failure.code}>{failure.code}: {failure.count}</span>) : <span>0</span>}
   <Best show={!skipped && row.operational_best.failures}/>
  </>;
  case 'cost': return <>
   <span>{row.cost.na ? `n/a — ${row.cost.na.reason}` : row.cost.per_run_usd===null ? 'n/a' : `$${row.cost.per_run_usd}`}</span>
   <small>n={row.cost.n} runs · per run</small><Best show={!skipped && row.operational_best.cost}/>
  </>;
  case 'time': return <>
   <span>{row.time.mean_seconds===null ? 'n/a' : `${row.time.mean_seconds} s`}</span>
   <small>n={row.time.n} runs</small><Best show={!skipped && row.operational_best.time}/>
  </>;
  default: return <Score cell={row[column]} of={sessions} skipped={skipped}/>;
 }
}

/** Overview displays the saved projection. Only leaderboard ordering happens here. */
export function Overview({data,state,navigate,legend,runId}:CompareTabProps<CompareOverview>) {
 const human = data.has_human && data.verdict.length > 0;
 const [sort,setSort]=useState<{key:Column;descending:boolean}>({key:'count',descending:false});
 const visible=columns.filter(column=>human || ['fails','cost','time'].includes(column.key));
 const activeSort=visible.some(column=>column.key===sort.key)?sort:{key:'fails' as const,descending:false};
 const rows=[...data.leaderboard].sort((a,b)=>{
  const av=sortValue(a,activeSort.key),bv=sortValue(b,activeSort.key);
  if(av===null)return bv===null?0:1;if(bv===null)return -1;
  return (av-bv)*(activeSort.descending?-1:1);
 });
 const changeSort=(column:typeof columns[number])=>setSort({key:column.key,descending:activeSort.key===column.key?!activeSort.descending:!!column.descending});
 const skipped=(key:string)=>data.leaderboard.find(row=>row.combo_key===key)?.na?.reason==='skipped: provider unavailable';
 const drill=(combo:string,metric?:string):CompareUrlState=>({...state,run:runId,view:'compare',tab:'deep',combos:[combo],combo,metric,code:undefined,session:undefined,turn:undefined,only:undefined});
 const activate=(event:MouseEvent<HTMLAnchorElement>,next:CompareUrlState)=>{
  if(event.button===0&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&!event.shiftKey){event.preventDefault();navigate(next);}
 };
 return <section className="overview-tab" aria-label="Overview results">
  <h2>Overview</h2>
  {human ? data.verdict.map((clause,index)=><p key={index} className="overview-verdict"><span>{clause.text}</span>{clause.claims.map((claim,i)=><small className="overview-claim" key={i} title={`${claim.metric}: ${claim.combo}`}>n={claim.n}</small>)}</p>) : <p>No human reference in this run</p>}
  {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Scroll containers need keyboard focus to scroll the table. */}
  <div className="overview-scroll" role="region" aria-label="Combo leaderboard" tabIndex={0}>
   <table className="overview-leaderboard" aria-label="Combo leaderboard"><thead><tr><th scope="col">Combo</th>{visible.map(column=><th key={column.key} scope="col" aria-sort={activeSort.key===column.key?(activeSort.descending?'descending':'ascending'):'none'}><button type="button" onClick={()=>changeSort(column)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();changeSort(column);}}}>{column.label}</button></th>)}</tr></thead>
    <tbody>{rows.map(row=>{const entry=legend.find(item=>item.combo.combo_key===row.combo_key),isSkipped=skipped(row.combo_key);return <tr key={row.combo_key}>
     <th scope="row"><EvalLink state={drill(row.combo_key)} navigate={navigate}>{entry?.letter??row.combo_key}</EvalLink>{isSkipped&&<span> — skipped</span>}<small>{entry?.label??row.combo_key}</small></th>
     {visible.map(column=><td key={column.key} data-label={column.label}>
      <LeaderScore row={row} column={column.key} skipped={isSkipped} sessions={data.header.sessions}/>
     </td>)}
    </tr>;})}</tbody>
   </table>
  </div>
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
  <div className="overview-footnotes">{data.footnotes.map((note,index)=><p key={index}>{note}</p>)}</div>
 </section>;
}
