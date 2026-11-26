import { useEffect, useRef, useState } from 'react';
import { EvalLink } from './CompareLink';
import type { CompareDeepDive, CompareOptions, NA, Snippet } from './compareApi';
import type { CompareTabProps } from './compareTypes';
import { GlobalsDotPlot } from './charts/GlobalsDotPlot';
import { MissBuckets } from './charts/MissBuckets';
import { CountBars } from './charts/CountBars';
import { PrfTable } from './charts/PrfTable';
import { ConfusionGrid } from './charts/ConfusionGrid';
import type { DotSeries } from './charts/dotPlotLayout';
import { ComboSelector, pairedSessions } from './charts/ComboSelector';
import { failedCombos } from './failedCombos';
import './deepDive.css';

const unavailable=(na:NA|undefined)=>`n/a${na?` - ${na.reason}`:''}`;
const metricNames:Record<string,string>={cct:'Cultivating change talk',sst:'Softening sustain talk',partnership:'Partnership',empathy:'Empathy'};
type Props=CompareTabProps<CompareDeepDive>;
function ReasoningPanel({code,combo,letter,count,api,runId,selected}:{code:string;combo?:string;letter:string;count:number|undefined;api:Props['api'];runId:string;selected:string[]}) {
 const [snippets,setSnippets]=useState<Snippet[]>([]);
 const [notes,setNotes]=useState<{session_id:string;turn_id:string;note:string}[]>([]);
 const [cursor,setCursor]=useState<string|null>();
 const [loading,setLoading]=useState(false);
 const [error,setError]=useState<string>();
 const pending=useRef<AbortController|null>(null);
 useEffect(()=>()=>pending.current?.abort(),[]);
 const load=async()=>{
  if(pending.current)return;
  const controller=new AbortController();pending.current=controller;setLoading(true);setError(undefined);
  try {
   const page=await api.compareReasoning(runId,{combos:selected,code,combo,cursor:cursor??undefined},controller.signal);
   if(!controller.signal.aborted){setSnippets(previous=>[...previous,...page.groups.filter(group=>group.code===code).flatMap(group=>group.snippets).filter(snippet=>snippet.combo_key===combo)]);setNotes(previous=>[...previous,...page.groups.filter(group=>group.code===code).flatMap(group=>group.human_notes??[])]);setCursor(page.next_cursor);}
  }catch(reason){if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:'Could not load reasoning.');}
  finally{if(!controller.signal.aborted){setLoading(false);pending.current=null;}}
 };
 return <section className="deep-reasoning-panel" aria-label={`${code} ${letter} reasoning`}><h5>{combo?`${letter} · ${count===undefined?'n/a':count} snippets`:'Human notes'}</h5>
  {!combo&&notes.map((note,index)=><article key={index}><p>{note.session_id} · {note.turn_id}</p><p className="deep-verbatim">{note.note===''?'withheld':note.note}</p></article>)}
  {!combo&&cursor===null&&!notes.length&&<p>No gold notes present</p>}
  {snippets.map((snippet,index)=><article key={index}><p>{snippet.session_id} · repeat {snippet.repeat}{snippet.turn_id&&` · ${snippet.turn_id}`}</p><p className="deep-verbatim">{snippet.rationale===''?'withheld':snippet.rationale}</p>{snippet.quote!==null&&snippet.quote!==undefined&&<blockquote>{snippet.quote}</blockquote>}{snippet.evidence?.map((evidence,i)=><blockquote key={i}>{evidence.turn_id}: {evidence.quote}</blockquote>)}</article>)}
  {loading&&<p role="status">Loading reasoning…</p>}{error&&<p role="alert">{error}</p>}
  {(cursor!==null||error)&&<button type="button" disabled={loading} aria-label={error?`Retry reasoning ${code} ${letter}`:cursor===undefined?combo?`Load reasoning ${code} ${letter}`:`Load human notes ${code}`:undefined} onClick={()=>void load()}>{error?'Retry':cursor===undefined?combo?'Load reasoning':'Load human notes':'Load more'}</button>}
 </section>;
}

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
   <section className="deep-reasoning"><h3>Reasoning roll-up</h3><p>Snippets load on request, up to 50 per page. Empty saved reasoning is shown as withheld.</p>{codes.map(code=><section key={code}><h4>{code}</h4><div className="deep-reasoning-columns"><section aria-label={`${code} Human`}><h5>Human</h5><p>Count: {data.counts.human?.[code]?.value??unavailable(data.counts.human?.[code]?.na)} · n={data.counts.human?.[code]?.n??0}</p><ReasoningPanel key={`${code}-human-${selected.join(',')}`} code={code} letter="Human" count={undefined} api={api} runId={runId} selected={selected}/></section>{shown.map(combo=><ReasoningPanel key={`${code}-${combo.combo_key}-${selected.join(',')}`} code={code} combo={combo.combo_key} letter={letter(combo.combo_key)} count={data.rationale_counts[code]?.[combo.combo_key]} api={api} runId={runId} selected={selected}/>)}</div></section>)}</section>
  </>}
 </div>;
}
