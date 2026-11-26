import { useEffect, useRef, useState } from 'react';
import { EvalLink } from './CompareLink';
import type { CompareDeepDive, CompareOptions } from './compareApi';
import type { CompareTabProps } from './compareTypes';
import { GlobalsDotPlot } from './charts/GlobalsDotPlot';
import { MissBuckets } from './charts/MissBuckets';
import { CountBars } from './charts/CountBars';
import { PrfTable } from './charts/PrfTable';
import { ConfusionGrid } from './charts/ConfusionGrid';
import { ReasoningRollup } from './charts/ReasoningRollup';
import type { DotSeries } from './charts/dotPlotLayout';
import { ComboSelector, pairedSessions } from './charts/ComboSelector';
import { failedCombos } from './failedCombos';
import './deepDive.css';

const metricNames:Record<string,string>={cct:'Cultivating change talk',sst:'Softening sustain talk',partnership:'Partnership',empathy:'Empathy'};
type Props=CompareTabProps<CompareDeepDive>;
function LineAgreement({data,legend,runId,navigate,state,api,series}:Props&{series:DotSeries[]}) {
 const selected=data.combos.map(combo=>combo.combo_key);
 const letter=(key:string)=>legend.find(item=>item.combo.combo_key===key)?.letter??key;
 const available=series.filter(item=>data.lines.combos[item.key]&&!data.lines.combos[item.key].lane);
 const [matches,setMatches]=useState<{options:CompareOptions;ids:string[]}|null>(null);
 const lastOptions=useRef<CompareOptions|undefined>(undefined);
 const [loading,setLoading]=useState(false);
 const [error,setError]=useState<string>();
 const pending=useRef<AbortController|null>(null);
 useEffect(()=>()=>pending.current?.abort(),[]);
 const find=async(options:CompareOptions)=>{
  lastOptions.current=options;pending.current?.abort();const controller=new AbortController();pending.current=controller;setLoading(true);setError(undefined);setMatches(null);
  try {
   const result=await api.compareLineMatches(runId,options,controller.signal);
   if(!controller.signal.aborted){setMatches({options,ids:result.session_ids});if(result.session_ids[0])navigate({...state,view:'compare',run:runId,tab:'lines',...options,session:result.session_ids[0],only:'disagree'});}
  }catch(reason){if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:'Could not load matching sessions.');}
  finally{if(!controller.signal.aborted)setLoading(false);}
 };
 if(data.lines.missing)return <section><h3>Per-line agreement</h3><p className="deep-empty">no line-level output ({data.lines.missing})</p></section>;
 return <section className="deep-lines"><h3>Per-line agreement</h3>
  {series.filter(item=>data.lines.combos[item.key]?.lane).map(item=><p key={item.key} className="deep-empty">no line-level output ({letter(item.key)})</p>)}
  {available.length>0&&<><PrfTable lines={data.lines} series={available}/>
   <ConfusionGrid combos={data.lines.combos} series={available} onSwitch={()=>{pending.current?.abort();setLoading(false);setError(undefined);setMatches(null);}} onMatch={pick=>void find({combos:selected,...pick})} footer={<>
    {loading&&<p role="status">Loading matching sessions…</p>}{error&&<div role="alert"><p>{error}</p><button type="button" onClick={()=>{if(lastOptions.current)void find(lastOptions.current);}}>Retry matching sessions</button></div>}{matches&&(matches.ids.length?<ul aria-label="Matching sessions">{matches.ids.map(session=><li key={session}><EvalLink state={{...state,view:'compare',run:runId,tab:'lines',...matches.options,session,only:'disagree'}} navigate={navigate}>{session}</EvalLink></li>)}</ul>:<p>No matching sessions</p>)}</>}/>
  </>}
 </section>;
}

export function DeepDive(props:Props) {
 const {data,legend,state,navigate,runId,api}=props;
 const selected=state.combos?.length?state.combos:data.combos.map(combo=>combo.combo_key);
 const failedAll=new Set(failedCombos(props.overview).filter(item=>item.all).map(item=>item.combo_key));
 const shown=data.combos.filter(combo=>selected.includes(combo.combo_key)&&!failedAll.has(combo.combo_key));
 const series:DotSeries[]=shown.map(combo=>{const index=Math.max(0,legend.findIndex(item=>item.combo.combo_key===combo.combo_key));return {key:combo.combo_key,letter:legend[index]?.letter??combo.combo_key,index,label:legend[index]?.label??combo.combo_key};});
 const letter=(key:string)=>legend.find(item=>item.combo.combo_key===key)?.letter??key;
 const sectionRefs=useRef<Record<string,HTMLElement|null>>({});
 useEffect(()=>{if(state.metric)sectionRefs.current[state.metric]?.scrollIntoView?.({block:'start'});},[state.metric,data]);
 const globals=Object.entries(data.globals.cells);
 const codes=Object.keys(data.counts.cells);
 return <div className="deep-dive"><h2>Deep dive</h2>
  <ComboSelector legend={legend} failed={failedCombos(props.overview)} selected={selected} paired={pairedSessions(props.overview,selected)} onChange={keys=>navigate({...state,view:'compare',run:runId,tab:'deep',combos:keys})}/>
  {!data.has_human?<p>no human reference</p>:<>
   <section><h3>Globals</h3><div className="deep-grid">{globals.map(([metric,cells])=>{
    const dots=data.globals.dots.filter(dot=>dot.metric===metric&&shown.some(combo=>combo.combo_key===dot.combo_key));
    return <section key={metric} ref={node=>{sectionRefs.current[metric]=node;}}><GlobalsDotPlot metric={metric} title={`${metricNames[metric]??metric} ratings`} dots={dots} series={series} cells={cells}/></section>;
   })}</div><MissBuckets globals={globals.map(([metric,cells])=>({metric,title:metricNames[metric]??metric,cells}))} series={series}/></section>
   <section><h3>Counts per code</h3><CountBars codes={codes} human={data.counts.human} cells={data.counts.cells} bias={data.counts.bias_pct} series={series} onSection={(code,node)=>{sectionRefs.current[code]=node;}}/></section>
   <LineAgreement key={selected.join(',')} {...props} series={series}/>
   <ReasoningRollup codes={codes} human={data.counts.human} rationaleCounts={data.rationale_counts} combos={shown.map(combo=>combo.combo_key)} letter={letter} api={api} runId={runId} selected={selected}/>
  </>}
 </div>;
}
