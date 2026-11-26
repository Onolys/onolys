import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ChartFrame } from './ChartFrame';
import { EvalLink } from './CompareLink';
import type { CompareCell, CompareDeepDive, CompareOptions, NA, Snippet } from './compareApi';
import type { CompareTabProps } from './compareTypes';
import { GlobalsDotPlot } from './charts/GlobalsDotPlot';
import { MissBuckets } from './charts/MissBuckets';
import type { DotSeries } from './charts/dotPlotLayout';
import { ComboSelector, pairedSessions } from './charts/ComboSelector';
import { failedCombos } from './failedCombos';
import './deepDive.css';

const unavailable=(na:NA|undefined)=>`n/a${na?` - ${na.reason}`:''}`;
const paired=(cell:CompareCell)=>`paired ${cell.n} of ${cell.of} · ${cell.repeats} repeats`;
const metricNames:Record<string,string>={cct:'Cultivating change talk',sst:'Softening sustain talk',partnership:'Partnership',empathy:'Empathy'};
type Props=CompareTabProps<CompareDeepDive>;
function Scroll({name,children}:{name:string;children:ReactNode}) {
 // Keyboard focus makes the wide chart or data table scrollable without a pointer.
 // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
 return <div className="table-scroll" role="region" aria-label={name} tabIndex={0}>{children}</div>;
}

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

function ConfusionGrid({current,combo,letter,selected,onMatch,interactive}:{current:CompareDeepDive['lines']['combos'][string];combo:string;letter:string;selected:string[];onMatch:(options:CompareOptions)=>void;interactive:boolean}) {
 const rows=Object.keys(current.confusion);
 const columns=[...new Set(Object.values(current.confusion).flatMap(row=>Object.keys(row)))];
 return <table aria-label={interactive?'Confusion grid':'Confusion data'}><caption>Human row vs {letter} column · {current.aligned} aligned lines · n={current.n}</caption><thead><tr><th scope="col">Human / combo</th>{columns.map(code=><th key={code} scope="col">{code}</th>)}</tr></thead><tbody>{rows.map(human=><tr key={human}><th scope="row">{human}</th>{columns.map(prediction=>{
  const value=current.confusion[human][prediction];
  return <td key={prediction}>{interactive?<button type="button" disabled={value===undefined||value===0} data-confusion-value={value??0} aria-label={`Human ${human}, ${letter} ${prediction}: ${value??0}`} onClick={()=>onMatch({combos:selected,combo,code:human,metric:prediction})}>{value??0}</button>:value??0}</td>;
 })}</tr>)}<tr><th scope="row">multi (multiple codes on either side)</th><td colSpan={Math.max(columns.length,1)}>{interactive?<button type="button" data-confusion-multi data-confusion-value={current.multi} disabled={!current.multi} onClick={()=>onMatch({combos:selected,combo,code:'multi',metric:'multi'})}>{current.multi}</button>:current.multi}</td></tr></tbody></table>;
}

function LineAgreement({data,legend,runId,navigate,state,api}:Props) {
 const selected=data.combos.map(combo=>combo.combo_key);
 const letter=(key:string)=>legend.find(item=>item.combo.combo_key===key)?.letter??key;
 const available=selected.filter(key=>data.lines.combos[key]&&!data.lines.combos[key].lane);
 const [choice,setChoice]=useState<string>();
 const key=choice&&available.includes(choice)?choice:available[0];
 const current=key?data.lines.combos[key]:undefined;
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
 if(data.lines.missing)return <section><h3>Per-line agreement</h3><p>no line-level output ({data.lines.missing})</p></section>;
 const prf=<table aria-label="Line agreement"><caption>Precision, recall and F1 by code and combo</caption><thead><tr><th scope="col">Code</th><th scope="col">Combo</th><th scope="col">Precision</th><th scope="col">Recall</th><th scope="col">F1</th><th scope="col">Sessions / aligned lines</th></tr></thead><tbody>{available.flatMap(combo=>Object.entries(data.lines.combos[combo]?.per_code??{}).map(([code,values])=><tr key={`${combo}-${code}`}><th scope="row">{code}</th><td>{letter(combo)}</td><td>{values.p??'n/a'}</td><td>{values.r??'n/a'}</td><td>{values.f1??'n/a'}</td><td>n={data.lines.combos[combo].n} · {data.lines.combos[combo].aligned} aligned · {data.lines.combos[combo].repeats} repeats</td></tr>))}</tbody></table>;
 return <section className="deep-lines"><h3>Per-line agreement</h3><p>{data.lines.codes_labeled.length} of 10 codes labeled</p>{data.lines.dataset_notes.map((note,index)=><p key={index}>{note}</p>)}
  {selected.filter(combo=>data.lines.combos[combo]?.lane).map(combo=><p key={combo}>no line-level output ({letter(combo)})</p>)}
  {available.length>0&&<><ChartFrame title="Precision / recall / F1" howToRead="Each value uses only the codes this dataset labels. n counts sessions; aligned lines and repeat counts come from the server." table={prf}><Scroll name="Line agreement results">{prf}</Scroll></ChartFrame>
   <label>Confusion combo <select aria-label="Confusion combo" value={key} onChange={event=>{pending.current?.abort();setLoading(false);setError(undefined);setChoice(event.target.value);setMatches(null);}}>{available.map(combo=><option key={combo} value={combo}>{letter(combo)}</option>)}</select></label>
   <ChartFrame title="Confusion" howToRead="Rows are human labels and columns are combo labels. The separate multi bucket includes lines with several codes on either side; those lines are excluded from the grid. Open a cell to find matching sessions in Line view." table={<ConfusionGrid current={current!} combo={key} letter={letter(key)} selected={selected} onMatch={options=>void find(options)} interactive={false}/>}><Scroll name="Confusion results"><ConfusionGrid current={current!} combo={key} letter={letter(key)} selected={selected} onMatch={options=>void find(options)} interactive/></Scroll></ChartFrame>
   {loading&&<p role="status">Loading matching sessions…</p>}{error&&<div role="alert"><p>{error}</p><button type="button" onClick={()=>{if(lastOptions.current)void find(lastOptions.current);}}>Retry matching sessions</button></div>}{matches&&(matches.ids.length?<ul aria-label="Matching sessions">{matches.ids.map(session=><li key={session}><EvalLink state={{...state,view:'compare',run:runId,tab:'lines',...matches.options,session,only:'disagree'}} navigate={navigate}>{session}</EvalLink></li>)}</ul>:<p>No matching sessions</p>)}
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
 const maxCount=Math.max(1,...Object.values(data.counts.cells).flatMap(cells=>Object.values(cells).map(cell=>cell.value??0)),...Object.values(data.counts.human??{}).map(cell=>cell.value??0));
 const globals=Object.entries(data.globals.cells);
 const codes=Object.keys(data.counts.cells);
 return <div className="deep-dive"><h2>Deep dive</h2>
  <ComboSelector legend={legend} failed={failedCombos(props.overview)} selected={selected} paired={pairedSessions(props.overview,selected)} onChange={keys=>navigate({...state,view:'compare',run:runId,tab:'deep',combos:keys})}/>
  {!data.has_human?<p>no human reference</p>:<>
   <section><h3>Globals</h3><div className="deep-grid">{globals.map(([metric,cells])=>{
    const dots=data.globals.dots.filter(dot=>dot.metric===metric&&shown.some(combo=>combo.combo_key===dot.combo_key));
    return <section key={metric} ref={node=>{sectionRefs.current[metric]=node;}}><GlobalsDotPlot metric={metric} title={`${metricNames[metric]??metric} ratings`} dots={dots} series={series} cells={cells}/></section>;
   })}</div><MissBuckets globals={globals.map(([metric,cells])=>({metric,title:metricNames[metric]??metric,cells}))} series={series}/></section>
   <section><h3>Counts</h3>{codes.map(code=>{
    const human=data.counts.human?.[code];
    const table=<table aria-label={`${code} counts`}><caption>Same-cohort count means and bias</caption><thead><tr><th scope="col">Reference / combo</th><th scope="col">Mean count</th><th scope="col">Bias</th><th scope="col">Paired sessions</th></tr></thead><tbody><tr><th scope="row">Human</th><td>{human?.value??unavailable(human?.na)}</td><td>Reference</td><td>n={human?.n??0}</td></tr>{shown.map(combo=>{const cell=data.counts.cells[code][combo.combo_key],bias=data.counts.bias_pct[code]?.[combo.combo_key];return <tr key={combo.combo_key}><th scope="row">{letter(combo.combo_key)}</th><td>{cell?.na||cell?.value===null?unavailable(cell?.na):cell?.value??'n/a'}</td><td>{bias?.na||bias?.value===null?unavailable(bias?.na):bias?.value??'n/a'}</td><td>{cell?paired(cell):'n/a'}</td></tr>;})}</tbody></table>;
    return <section key={code} ref={node=>{sectionRefs.current[code]=node;}}><ChartFrame title={`${code} counts`} howToRead="Human and combo bars use the same paired cohort supplied by the server. Bias words describe the saved percentage; n/a retains the server’s reason." table={table}>
     <div className="deep-count-row" data-human-count={code}><strong>Human</strong><div className="deep-count-track"><span style={{width:`${(human?.value??0)/maxCount*100}%`}}/></div><span>{human?.value??unavailable(human?.na)} · n={human?.n??0}</span></div>
     {shown.map(combo=>{const cell=data.counts.cells[code][combo.combo_key],bias=data.counts.bias_pct[code]?.[combo.combo_key];return <div key={combo.combo_key} className="deep-count-row"><strong>{letter(combo.combo_key)}</strong><div className="deep-count-track"><span style={{width:`${(cell?.value??0)/maxCount*100}%`}}/></div><span>{cell?.na||cell?.value===null?unavailable(cell?.na):cell?.value??'n/a'} · {cell?paired(cell):'n/a'}</span><span>{!bias||bias.na||bias.value===null?unavailable(bias?.na):bias.value>0?`over-counts by ${bias.value}%`:bias.value<0?`under-counts by ${Math.abs(bias.value)}%`:'no count bias'}</span></div>;})}
    </ChartFrame></section>;
   })}</section>
   <LineAgreement key={selected.join(',')} {...props}/>
   <section className="deep-reasoning"><h3>Reasoning roll-up</h3><p>Snippets load on request, up to 50 per page. Empty saved reasoning is shown as withheld.</p>{codes.map(code=><section key={code}><h4>{code}</h4><div className="deep-reasoning-columns"><section aria-label={`${code} Human`}><h5>Human</h5><p>Count: {data.counts.human?.[code]?.value??unavailable(data.counts.human?.[code]?.na)} · n={data.counts.human?.[code]?.n??0}</p><ReasoningPanel key={`${code}-human-${selected.join(',')}`} code={code} letter="Human" count={undefined} api={api} runId={runId} selected={selected}/></section>{shown.map(combo=><ReasoningPanel key={`${code}-${combo.combo_key}-${selected.join(',')}`} code={code} combo={combo.combo_key} letter={letter(combo.combo_key)} count={data.rationale_counts[code]?.[combo.combo_key]} api={api} runId={runId} selected={selected}/>)}</div></section>)}</section>
  </>}
 </div>;
}
