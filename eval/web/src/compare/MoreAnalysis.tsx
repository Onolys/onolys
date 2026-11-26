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

export function MoreAnalysis({data, overview, legend, runId, navigate}: CompareTabProps<CompareAnalysis>) {
 return <div className="more-analysis">
  <h2>More analysis</h2>
  <BaselineCard baseline={data.baseline}/>
  <ReliabilityTable data={data} legend={legend} failed={failedCombos(overview)} best={Object.fromEntries(overview.leaderboard.map(row=>[row.combo_key,{failures:row.operational_best.failures,time:row.operational_best.time}]))}/>
  {!data.has_human ? <p>no human reference</p> : <>
   <CostAccuracyScatter data={data} legend={legend} failed={failedCombos(overview)}/>
   <Disclosure label="Show head-to-head"><HeadToHead data={data} legend={legend} failed={failedCombos(overview)}/></Disclosure>
   <Disclosure label="Show interviews by combo"><InterviewGrid data={data} legend={legend} failed={failedCombos(overview)} runId={runId} navigate={navigate}/></Disclosure>
   <Disclosure label="Show error vs interview length"><ErrorVsLength data={data} legend={legend} failed={failedCombos(overview)}/></Disclosure>
  </>}
 </div>;
}
