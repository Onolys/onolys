import { Disclosure } from '../ui/Disclosure';
import { HeadToHead } from './charts/HeadToHead';
import { InterviewGrid } from './charts/InterviewGrid';
import { ErrorVsLength } from './charts/ErrorVsLength';
import type { CompareAnalysis } from './compareApi';
import type { CompareTabProps } from './compareTypes';
import { CostAccuracyScatter } from './charts/CostAccuracyScatter';
import { BaselineCard } from './charts/BaselineCard';
import { ReliabilityTable } from './charts/ReliabilityTable';
import { failedCombos } from './failedCombos';
import './moreAnalysis.css';

const note = (text: string) => <p className="more-analysis-note">{text}</p>;

/** More analysis: cost vs accuracy and reliability are always shown; everything else sits behind a verb toggle (bias to less). */
export function MoreAnalysis({data, overview, legend, runId, navigate}: CompareTabProps<CompareAnalysis>) {
 const failed = failedCombos(overview);
 const best = Object.fromEntries(overview.leaderboard.map(row => [row.combo_key, {failures: row.operational_best.failures, time: row.operational_best.time}]));
 return <div className="more-analysis">
  <h2>More analysis</h2>
  {data.has_human ? <CostAccuracyScatter data={data} legend={legend} failed={failed}/> : note('No human reference, so error charts are hidden.')}
  <ReliabilityTable data={data} legend={legend} failed={failed} best={best}/>
  <div className="more-analysis-toggles">
   {data.has_human && <>
    <Disclosure label="Show error vs interview length"><ErrorVsLength data={data} legend={legend} failed={failed}/></Disclosure>
    <Disclosure label="Show head-to-head"><HeadToHead data={data} legend={legend} failed={failed}/></Disclosure>
    <Disclosure label="Show interviews by combo"><InterviewGrid data={data} legend={legend} failed={failed} runId={runId} navigate={navigate}/></Disclosure>
   </>}
   <Disclosure label="Show human-vs-human baseline"><BaselineCard baseline={data.baseline}/></Disclosure>
  </div>
 </div>;
}
