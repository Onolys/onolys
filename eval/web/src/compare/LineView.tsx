import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Button, Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@onolys/ui';
import { ApiError } from '../api';
import type { CompareLines, CompareReasoning, CompareTurn, ModelLane, Snippet } from './compareApi';
import type { CompareTabProps } from './compareTypes';
import './lineView.css';
const codes=['affirm','confront','cr','emphasize_autonomy','gi','persuade','persuade_permission','question','seek_collab','sr','none','multi'];
const label=(value:string[])=>value.length?value.join(', '):'none';
const category=(value:string[])=>value.length>1?'multi':value[0]??'none';
const same=(a:string[],b:string[])=>a.length===b.length&&a.every(code=>b.includes(code));
function ScrollRegion({name,children}:{name:string;children:ReactNode}) {
 // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- Keyboard users must be able to scroll the transcript and rating tables.
 return <div className="table-scroll" role="region" aria-label={name} tabIndex={0}>{children}</div>;
}
function ErrorNotice({error,retry}:{error:unknown;retry:()=>void}) {
 return <div role="alert">{error instanceof ApiError&&error.code==='transcript_changed'?'The saved transcript changed since this run; lines cannot be shown.':error instanceof Error?error.message:'Could not load saved output.'}<Button onClick={retry}>Retry</Button></div>;
}
function Snippets({snippets}:{snippets:Snippet[]}) {
 return <>{snippets.map((snippet,i)=><article key={i}><p>Repeat {snippet.repeat}</p><p className="line-verbatim">{snippet.rationale===''?'withheld':snippet.rationale}</p>{snippet.quote_verified&&snippet.quote!=null&&<blockquote className="line-verbatim">{snippet.quote}</blockquote>}{snippet.evidence?.map((item,j)=><blockquote key={j}><span>{item.turn_id}</span><p className="line-verbatim">{item.quote}</p></blockquote>)}</article>)}</>;
}
function Globals({data,api,runId,selected}:{data:CompareLines;api:CompareTabProps<CompareLines>['api'];runId:string;selected:string[]}) {
 const [page,setPage]=useState<CompareReasoning>();const [error,setError]=useState<unknown>();const [attempt,setAttempt]=useState(0);const [cursor,setCursor]=useState<string>();const [pending,setPending]=useState(true);
 const keys=JSON.stringify(selected);
 useEffect(()=>{
  const controller=new AbortController();
  api.compareReasoning(runId,{session:data.session_id,kind:'global',combos:JSON.parse(keys) as string[],...(cursor?{cursor}:{})},controller.signal).then(value=>{if(!controller.signal.aborted){setPage(old=>cursor&&old?{...value,groups:[...old.groups,...value.groups]}:value);setError(undefined);setPending(false);}}).catch(reason=>{if(!controller.signal.aborted){setError(reason);setPending(false);}});
  return ()=>controller.abort();
 },[api,runId,data.session_id,keys,cursor,attempt]);
 const metrics=Array.from(new Set([...Object.keys(data.globals.human),...Object.values(data.globals.combos).flatMap(rows=>rows.flatMap(row=>Object.keys(row)))]));
 return <section><h3>Session globals</h3><ScrollRegion name="Session global ratings"><table><caption>Human and saved combo ratings by repeat</caption><thead><tr><th scope="col">Global</th><th scope="col">Human</th>{selected.map(key=><th scope="col" key={key}>{key}</th>)}</tr></thead><tbody>{metrics.map(metric=><tr key={metric}><th scope="row">{metric}</th><td>{data.globals.human[metric]??'n/a'}</td>{selected.map(key=><td key={key}>{data.globals.combos[key]?.length?data.globals.combos[key].map(row=>row[metric]??'n/a').join(' / '):'n/a'}<Snippets snippets={page?.groups.filter(group=>group.code===metric).flatMap(group=>group.snippets.filter(snippet=>snippet.combo_key===key))??[]}/></td>)}</tr>)}</tbody></table></ScrollRegion><p>How to read: Ratings and reasons are saved output. Each rating is shown in repeat order; evidence quotes are verified by the server.</p>{pending&&<p role="status">Loading global reasons…</p>}{error!==undefined&&<ErrorNotice error={error} retry={()=>{setPending(true);setAttempt(n=>n+1);}}/>}{page?.next_cursor&&<Button disabled={pending} onClick={()=>{setPending(true);setCursor(page.next_cursor!);}}>Load more global reasons</Button>}</section>;
}
export function LineView({data,overview,state,navigate,legend,api,runId}:CompareTabProps<CompareLines>) {
 const [expanded,setExpanded]=useState<Record<string,boolean>>({});const [popup,setPopup]=useState<{key:string;data?:CompareTurn;error?:unknown}>();const [attempt,setAttempt]=useState(0);
 const returnFocus=useRef<HTMLElement|null>(null);const triggers=useRef<Record<string,HTMLButtonElement|null>>({});
 const selected=state.combos?.length?state.combos:data.combos.map(combo=>combo.combo_key),keys=JSON.stringify(selected);
 const popupKey=JSON.stringify([data.session_id,state.turn,keys]);
 useEffect(()=>{
  if(!state.turn||!data.has_human||data.missing==='human'||data.missing==='both')return;const controller=new AbortController();
  returnFocus.current=returnFocus.current??triggers.current[state.turn];
  api.compareTurn(runId,data.session_id,state.turn,{combos:JSON.parse(keys) as string[]},controller.signal).then(value=>{if(!controller.signal.aborted)setPopup({key:popupKey,data:value});}).catch(error=>{if(!controller.signal.aborted)setPopup({key:popupKey,error});});
  return ()=>controller.abort();
 },[api,runId,data.session_id,data.has_human,data.missing,state.turn,keys,popupKey,attempt]);
 const change=(next:Partial<typeof state>)=>navigate({...state,...next,view:'compare',run:runId,tab:'lines',turn:undefined});
 const letter=(key:string)=>legend.find(item=>item.combo.combo_key===key)?.letter??key;
 const lane=(key:string)=>data.lanes[key] as ModelLane|undefined;
 if(!data.has_human)return <p>no human reference</p>;
 if(data.missing==='human'||data.missing==='both'||data.gold.utterance_codes===null)return <p>no line-level output (human)</p>;
 const human=data.lanes.human??{};
 const turns=data.turns.filter(turn=>{
  if(state.only==='disagree'&&!data.disagreement[turn.id])return false;
  if(state.code==='multi'&&state.metric==='multi')return human[turn.id]!==undefined&&([human[turn.id],...(state.combo?lane(state.combo)?.turns[turn.id]??[]:[])].some(row=>category(row)==='multi'));
  if(state.code&&(human[turn.id]===undefined||category(human[turn.id])!==state.code))return false;
  if(state.metric){const lanes=state.combo?[state.combo]:selected;if(!lanes.some(key=>lane(key)?.turns[turn.id]?.some(row=>category(row)===state.metric)))return false;}
  return true;
 });
 const active=popup?.key===popupKey?popup:undefined;
 return <section className="line-view"><h2>Line view</h2><div className="line-filters"><label>Session<select value={state.session??data.session_id} onChange={event=>change({session:event.target.value})}>{(overview.header.line_sessions??[{session_id:data.session_id,matched_lines:null}]).map(item=><option key={item.session_id} value={item.session_id}>{item.session_id} · {item.matched_lines===null?'unavailable':`${item.matched_lines} matched lines`}</option>)}</select></label><label>Human code<select value={state.code??''} onChange={event=>change({code:event.target.value||undefined})}><option value="">All codes</option>{codes.map(code=><option key={code}>{code}</option>)}</select></label><label>Prediction code<select value={state.metric??''} onChange={event=>change({metric:event.target.value||undefined})}><option value="">All predictions</option>{codes.map(code=><option key={code}>{code}</option>)}</select></label><label>Combo<select value={state.combo??''} onChange={event=>change({combo:event.target.value||undefined})}><option value="">All selected combos</option>{selected.map(key=><option key={key} value={key}>{letter(key)} · {key}</option>)}</select></label><label><input type="checkbox" checked={state.only==='disagree'} onChange={event=>change({only:event.target.checked?'disagree':undefined})}/>Only disagreements</label></div>
 <fieldset><legend>Combo lanes</legend>{legend.map(item=><label key={item.combo.combo_key}><input type="checkbox" checked={selected.includes(item.combo.combo_key)} onChange={event=>{const next=event.target.checked?[...selected,item.combo.combo_key]:selected.filter(key=>key!==item.combo.combo_key);if(next.length)change({combos:next});}}/>{item.letter} · {item.label}</label>)}</fieldset>
 <p>How to read: Human cells are blank when no label was saved; none means an explicitly empty label. ⚠ marks a disagreement. Combo codes appear in repeat order.</p>
 <ScrollRegion name="Transcript lanes"><table><caption>Transcript and saved line codes</caption><thead><tr><th scope="col">Turn</th><th scope="col">Speaker</th><th scope="col">Transcript</th><th scope="col">Human</th><th scope="col">Combo lanes</th></tr></thead><tbody>{turns.map(turn=>{
 const differing=selected.filter(key=>{const item=lane(key);return !item||item.missing||human[turn.id]===undefined||item.turns[turn.id]?.some(row=>!same(row,human[turn.id]));});const agreeing=selected.filter(key=>!differing.includes(key));
 const shown=selected.length>5&&!expanded[turn.id]?differing:selected;
 return <tr key={turn.id} data-turn={turn.id} className={data.disagreement[turn.id]?'line-disagree':undefined}><th scope="row"><button type="button" ref={node=>{triggers.current[turn.id]=node;}} aria-label={`Inspect turn ${turn.id}`} onClick={event=>{returnFocus.current=event.currentTarget;navigate({...state,view:'compare',run:runId,tab:'lines',turn:turn.id});}}>{turn.id}</button>{data.disagreement[turn.id]&&<span aria-label="Disagreement"> ⚠</span>}</th><td className="line-verbatim">{turn.speaker}</td><td data-transcript className="line-verbatim">{turn.text}</td><td data-human>{human[turn.id]===undefined?'':label(human[turn.id])}</td><td>{shown.map(key=><p className="line-chip" key={key}>{!lane(key)||lane(key)?.missing?<><span>{letter(key)}: </span><span>no line-level output</span></>:`${letter(key)}: ${lane(key)?.turns[turn.id]?.map(label).join(' / ')??''}`}</p>)}{selected.length>5&&agreeing.length>0&&<button type="button" onClick={()=>setExpanded(old=>({...old,[turn.id]:!old[turn.id]}))}>{expanded[turn.id]?'Collapse agreement':`+${agreeing.length} agree`}</button>}</td></tr>;
 })}</tbody></table></ScrollRegion>{turns.length===0&&<p>No matching lines</p>}{data.dataset_notes.map((note,i)=><p key={i} className="line-verbatim">{note}</p>)}
 <Globals key={`${data.session_id}-${keys}`} data={data} api={api} runId={runId} selected={selected}/>
 <Dialog open={Boolean(state.turn)} onOpenChange={open=>{if(!open)navigate({...state,turn:undefined});}}><DialogContent className="line-dialog" onCloseAutoFocus={event=>{event.preventDefault();(returnFocus.current??(state.turn?triggers.current[state.turn]:null))?.focus();}}><DialogHeader><DialogTitle>Turn {state.turn}</DialogTitle><DialogDescription>Saved human labels and combo output</DialogDescription></DialogHeader>{!active&&<p role="status">Loading line…</p>}{active?.error!==undefined&&<ErrorNotice error={active.error} retry={()=>setAttempt(n=>n+1)}/>}{active?.data&&<><p className="line-verbatim">{active.data.text}</p><h3>Human</h3><p>{active.data.human?label(active.data.human.codes):''}</p>{active.data.human?.note!=null&&<p className="line-verbatim">{active.data.human.note}</p>}{selected.map(key=>{const item=active.data!.combos[key];return <section key={key}><h3>{letter(key)} · {key}</h3>{!item||item.missing?<p>no line-level output</p>:<><p>{item.codes.map(label).join(' / ')}</p><Snippets snippets={item.rationales}/>{item.agree&&<p>{item.agree.k} of {item.agree.r} repeats agree</p>}</>}</section>;})}</>}</DialogContent></Dialog>
 </section>;
}
