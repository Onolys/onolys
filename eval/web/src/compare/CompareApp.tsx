import { useEffect, useRef, useState } from 'react';
import { Button } from '@onolys/ui';
import { ApiError, type EvalApi, type RunDetail } from '../api';
import type { CompareAnalysis, CompareDeepDive, CompareLines, CompareOverview } from './compareApi';
import { EvalLink, type CompareNavigate } from './CompareLink';
import type { ComboLegendEntry } from './compareTypes';
import type { CompareTab, CompareUrlState } from './compareUrl';
import { ComboLegend } from './ComboLegend';
import { failedCombos } from './failedCombos';
import { ComparisonHeader } from './ComparisonHeader';
import { Overview } from './Overview';
import { DeepDive } from './DeepDive';
import { MoreAnalysis } from './MoreAnalysis';
import { LineView } from './LineView';
import { MAX_LANES } from './line/LaneTable';
import './compare.css';
const tabs: {id:CompareTab;label:string}[] = [{id:'overview',label:'Overview'},{id:'deep',label:'Deep dive'},{id:'more',label:'More analysis'},{id:'lines',label:'Line view'}];
type Projection = CompareOverview | CompareDeepDive | CompareAnalysis | CompareLines;
type Entry = {data?:Projection;error?:unknown};
export function comboLetter(index:number):string {
 let result='';for(let n=index+1;n>0;n=Math.floor((n-1)/26))result=String.fromCharCode(65+(n-1)%26)+result;return result;
}
function Failure({error,runId,navigate,retry}:{error:unknown;runId:string;navigate:CompareNavigate;retry:()=>void}) {
 if(error instanceof ApiError && error.status===404)return <div role="alert"><p>Run not found</p><EvalLink state={{view:'history'}} navigate={navigate}>History</EvalLink></div>;
 if(error instanceof ApiError && error.status===409 && ['no_completed_runs','not_finished'].includes(error.code??''))return <div role="alert"><p>No completed runs to compare yet</p><EvalLink state={{view:'run',run:runId}} navigate={navigate}>Back to run</EvalLink></div>;
 if(error instanceof ApiError && error.status===409 && error.code==='transcript_changed')return <div role="alert"><p>The saved transcript changed since this run; lines cannot be shown.</p></div>;
 return <div role="alert"><p>{error instanceof Error ? error.message : 'Could not load comparison. Please try again.'}</p><Button onClick={retry}>Retry</Button></div>;
}
/** Remount for a new run; completed tab requests are cached until this page is left. */
export function CompareApp({api,runId,state,navigate}:{api:EvalApi;runId:string;state:CompareUrlState;navigate:CompareNavigate}) {
 const [overview,setOverview]=useState<{data?:CompareOverview;error?:unknown}>({});
 const [run,setRun]=useState<RunDetail>();
 const [cache,setCache]=useState<Record<string,Entry>>({});
 const [overviewAttempt,setOverviewAttempt]=useState(0);
 const [tabAttempt,setTabAttempt]=useState(0);
 const tabRefs=useRef<(HTMLButtonElement|null)[]>([]);
 const tab=state.tab??'overview';
 const defaults=overview.data?.combos.filter(combo=>{const cell=overview.data!.count_error[combo.combo_key];return cell && !cell.na && cell.off!==null;}).sort((a,b)=>overview.data!.count_error[a.combo_key].off!-overview.data!.count_error[b.combo_key].off!).slice(0,3).map(combo=>combo.combo_key)??[];
 const shownLanes=(()=>{
  const base=(state.combos?.length?state.combos:overview.data?.combos.map(combo=>combo.combo_key)??[]).slice(0,MAX_LANES);
  return state.combo&&!base.includes(state.combo)?[...base.slice(0,MAX_LANES-1),state.combo]:base;
 })();
 const effectiveCombos=tab==='deep'&&!state.combos?.length?defaults:tab==='lines'?shownLanes:state.combos??[];
 const combosKey=JSON.stringify(effectiveCombos);
 const [matches,setMatches]=useState<Record<string,{session_ids?:string[];error?:unknown}>>({});
 const matchKey=JSON.stringify([combosKey,state.code,state.metric,state.combo]);
 const filtered=Boolean(state.code&&state.metric&&state.combo);
 const match=matches[matchKey];
 const sessions=overview.data?.header.line_sessions??[];
 const rankedSessions=[...sessions].sort((a,b)=>(b.matched_lines??-1)-(a.matched_lines??-1));
 const defaultSession=rankedSessions[0]?.session_id;
 const matchedSession=rankedSessions.find(item=>match?.session_ids?.includes(item.session_id))?.session_id??match?.session_ids?.[0];
 const session=state.session ?? (filtered?matchedSession:defaultSession);
 useEffect(()=>{
  if(tab!=='lines'||state.session||!filtered||match||!overview.data)return;
  const controller=new AbortController();
  api.compareLineMatches(runId,{combos:JSON.parse(combosKey) as string[],code:state.code,metric:state.metric,combo:state.combo},controller.signal).then(value=>{if(!controller.signal.aborted)setMatches(old=>({...old,[matchKey]:value}));}).catch(error=>{if(!controller.signal.aborted)setMatches(old=>({...old,[matchKey]:{error}}));});
  return ()=>controller.abort();
 },[api,runId,tab,state.session,filtered,match,overview.data,combosKey,state.code,state.metric,state.combo,matchKey]);
 const cacheKey=JSON.stringify([tab,combosKey,tab==='lines'?session:null,tab==='lines'?null:state.code,tab==='lines'?null:state.combo]);
 const entry=cache[cacheKey];
 useEffect(()=>{
  const controller=new AbortController();
  api.compareOverview(runId,{},controller.signal).then(data=>{if(!controller.signal.aborted)setOverview({data});}).catch(error=>{if(!controller.signal.aborted)setOverview({error});});
  return ()=>controller.abort();
 },[api,runId,overviewAttempt]);
 useEffect(()=>{
  const controller=new AbortController();
  api.run(runId,controller.signal).then(value=>{if(!controller.signal.aborted)setRun(value);}).catch(()=>{/* Supplemental saved labels do not block the Compare projection. */});
  return ()=>controller.abort();
 },[api,runId]);
 useEffect(()=>{
  if(tab==='overview'||entry||!overview.data||(tab==='lines'&&!session))return;
  const controller=new AbortController();
  const options={combos:JSON.parse(combosKey) as string[],code:state.code,combo:state.combo};
  const request=tab==='deep'?api.compareDeepDive(runId,options,controller.signal):tab==='more'?api.compareAnalysis(runId,options,controller.signal):api.compareLines(runId,session!,options,controller.signal);
  request.then(data=>{if(!controller.signal.aborted)setCache(previous=>({...previous,[cacheKey]:{data}}));}).catch(error=>{if(!controller.signal.aborted)setCache(previous=>({...previous,[cacheKey]:{error}}));});
  return ()=>controller.abort();
 },[api,runId,tab,entry,overview.data,session,combosKey,state.code,state.combo,cacheKey,tabAttempt]);
 const retryOverview=()=>{setOverview({});setOverviewAttempt(n=>n+1);};
 if(overview.error)return <Failure error={overview.error} runId={runId} navigate={navigate} retry={retryOverview}/>;
 if(!overview.data)return <p role="status">Loading Compare…</p>;
 const data=overview.data;
 const active=tab==='overview'?data:entry?.data;
 const legend:ComboLegendEntry[]=data.combos.map((combo,index)=>{
  const savedLabel=run?.combo_labels?.[combo.combo_key] ?? run?.combo_labels?.[combo.combo_key.slice(combo.combo_key.indexOf('|')+1)];
  return {letter:comboLetter(index),combo,label:savedLabel ? `${combo.engine} · ${savedLabel}` : [combo.engine,combo.model,combo.tier,combo.effort,combo.combo_key].filter(Boolean).join(' · ')};
 });
 const failed=failedCombos(data);
 const props={overview:data,run,state:tab==='deep'?{...state,combos:effectiveCombos}:tab==='lines'?{...state,combos:effectiveCombos,session}:state,navigate,legend,api,runId};
 const cohorts=tab==='deep'?(active&&'cohorts' in active?active.cohorts??{}:{}):data.cohorts;
 const retryTab=()=>{setCache(previous=>{const next={...previous};delete next[cacheKey];return next;});setTabAttempt(n=>n+1);};
 return <section className="compare-app"><ComparisonHeader data={data} run={run} runId={runId} navigate={navigate} legend={legend} cohorts={cohorts}/>
 <ComboLegend legend={legend} failed={failed} state={state} navigate={navigate}/>
 <div role="tablist" aria-label="Compare screens">{tabs.map((item,index)=><button key={item.id} ref={node=>{tabRefs.current[index]=node;}} type="button" role="tab" id={`compare-tab-${item.id}`} aria-selected={tab===item.id} aria-controls="compare-panel" tabIndex={tab===item.id?0:-1} onClick={()=>navigate({...state,view:'compare',run:runId,tab:item.id})} onKeyDown={event=>{
  let next:number;if(event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;
  event.preventDefault();tabRefs.current[next]?.focus();navigate({...state,view:'compare',run:runId,tab:tabs[next].id});
 }}>{item.label}</button>)}</div>
 <div role="tabpanel" id="compare-panel" aria-labelledby={`compare-tab-${tab}`} tabIndex={0}>{entry?.error?<Failure error={entry.error} runId={runId} navigate={navigate} retry={retryTab}/>:tab==='overview'?<Overview {...props} data={data}/>:tab==='lines'&&!session?(match?.error?<Failure error={match.error} runId={runId} navigate={navigate} retry={()=>setMatches(old=>{const next={...old};delete next[matchKey];return next;})}/>:<p role={filtered&&!match?'status':undefined}>{filtered&&!match?'Loading matching sessions…':filtered?'No matching sessions':'No sessions available'}</p>):!active?<p role="status">Loading {tabs.find(item=>item.id===tab)?.label}…</p>:tab==='deep'?<DeepDive {...props} data={active as CompareDeepDive}/>:tab==='more'?<MoreAnalysis {...props} data={active as CompareAnalysis}/>:<LineView {...props} data={active as CompareLines}/>}</div></section>;
}
