import type { CompareOverview } from './compareApi';
import type { CompareTabProps } from './compareTypes';
import { MetricHeatmap } from './MetricHeatmap';
import { Leaderboard } from './Leaderboard';
import { failedCombos } from './failedCombos';
import { Chip } from '../ui/Chip';
import { Disclosure } from '../ui/Disclosure';
import { Note } from '../ui/Note';
import './overview.css';

function Verdict({data,legend,human}:{data:CompareOverview;legend:CompareTabProps<CompareOverview>['legend'];human:boolean}) {
 const failed=failedCombos(data).filter(item=>item.all);
 const letter=(key:string)=>legend.find(item=>item.combo.combo_key===key)?.letter??key;
 return <div className="overview-verdict-block">
  {human ? data.verdict.map((clause,index)=><p key={index} className="overview-verdict"><span>{clause.text}</span>{clause.claims.map((claim,i)=><small className="overview-claim" key={i} title={`${claim.metric}: ${claim.combo}`}>n={claim.n}</small>)}</p>)
   : <div className="overview-empty"><Chip tone="info">No human reference in this run</Chip><span>Only failures, cost and time are compared.</span></div>}
  {failed.length>0&&<Note>Excluded from best: {failed.map(item=>`${letter(item.combo_key)} (all runs failed: ${item.code})`).join(', ')}.</Note>}
 </div>;
}

/** Overview: verdict, leaderboard, one muted notes block; the heatmap is secondary and collapsed. */
export function Overview({data,state,navigate,legend,runId}:CompareTabProps<CompareOverview>) {
 const human = data.has_human && data.verdict.length > 0;
 return <section className="overview-tab" aria-label="Overview results">
  <Verdict data={data} legend={legend} human={human}/>
  <Leaderboard data={data} legend={legend} state={state} navigate={navigate} runId={runId}/>
  <Note>Count error: average tallies missed per session. Globals within ±1: ratings within one point of human. Cost and Time are operational, not compared with human. Sessions have equal weight; repeats are averaged first. Time may read short for retried units.</Note>
  {human&&<Disclosure label="Show metric heatmap"><MetricHeatmap data={data} legend={legend} state={state} navigate={navigate} runId={runId}/></Disclosure>}
 </section>;
}
