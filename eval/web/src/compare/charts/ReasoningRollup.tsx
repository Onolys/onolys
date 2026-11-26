import { useEffect, useMemo, useRef, useState } from 'react';
import { Disclosure } from '../../ui/Disclosure';
import { Note } from '../../ui/Note';
import type { CompareDeepDive, NA, Snippet } from '../compareApi';
import type { CompareTabProps } from '../compareTypes';
import '../deepDive.css';

interface PanelCache{snippets:Snippet[];notes:{session_id:string;turn_id:string;note:string}[];cursor:string|null|undefined}
type Cache=Map<string,PanelCache>;
type Api=CompareTabProps<CompareDeepDive>['api'];
const unavailable=(na:NA|undefined)=>`n/a${na?` - ${na.reason}`:''}`;
function ReasoningPanel({code,combo,letter,count,api,runId,selected,cache}:{cache:Cache;code:string;combo?:string;letter:string;count:number|undefined;api:Api;runId:string;selected:string[]}) {
 const cacheKey=`${code}|${combo??'human'}`;
 const known=cache.get(cacheKey);
 const empty=combo!==undefined&&count===0;
 const [snippets,setSnippets]=useState<Snippet[]>(known?.snippets??[]);
 const [notes,setNotes]=useState<{session_id:string;turn_id:string;note:string}[]>(known?.notes??[]);
 const [cursor,setCursor]=useState<string|null|undefined>(empty?null:known?.cursor);
 const [loading,setLoading]=useState(!empty&&known===undefined);
 const [error,setError]=useState<string>();
 const pending=useRef<AbortController|null>(null);
 const run=async()=>{
  if(pending.current)return;
  const controller=new AbortController();pending.current=controller;
  try {
   const page=await api.compareReasoning(runId,{combos:selected,code,combo,cursor:cursor??undefined},controller.signal);
   if(!controller.signal.aborted){setSnippets(previous=>[...previous,...page.groups.filter(group=>group.code===code).flatMap(group=>group.snippets).filter(snippet=>snippet.combo_key===combo)]);setNotes(previous=>[...previous,...page.groups.filter(group=>group.code===code).flatMap(group=>group.human_notes??[])]);setCursor(page.next_cursor);}
  }catch(reason){if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:'Could not load reasoning.');}
  finally{if(!controller.signal.aborted){setLoading(false);pending.current=null;}}
 };
 useEffect(()=>{if(!loading&&!error&&cursor!==undefined)cache.set(cacheKey,{snippets,notes,cursor});},[cache,cacheKey,snippets,notes,cursor,loading,error]);
 const load=()=>{setLoading(true);setError(undefined);return run();};
 // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
 useEffect(()=>{if(!empty&&cache.get(cacheKey)===undefined)void run();return()=>{pending.current?.abort();pending.current=null;};},[]);
 return <section className="deep-reasoning-panel" aria-label={`${code} ${letter} reasoning`}><h5>{combo?`${letter} · ${count===undefined?'n/a':count} snippets`:'Human notes'}</h5>
  {!combo&&notes.map((note,index)=><article key={index}><p>{note.session_id} · {note.turn_id}</p><p className="deep-verbatim">{note.note===''?'withheld':note.note}</p></article>)}
  {!combo&&cursor===null&&!notes.length&&<p>No gold notes present</p>}
  {snippets.map((snippet,index)=><article key={index}><p>{snippet.session_id} · repeat {snippet.repeat}{snippet.turn_id&&` · ${snippet.turn_id}`}</p><p className="deep-verbatim">{snippet.rationale===''?'withheld':snippet.rationale}</p>{snippet.quote!==null&&snippet.quote!==undefined&&<blockquote>{snippet.quote}</blockquote>}{snippet.evidence?.map((evidence,i)=><blockquote key={i}>{evidence.turn_id}: {evidence.quote}</blockquote>)}</article>)}
  {loading&&<p role="status">Loading reasoning…</p>}{error&&<p role="alert">{error}</p>}
  {(cursor!==null||error)&&<button type="button" disabled={loading} aria-label={error?`Retry reasoning ${code} ${letter}`:cursor===undefined?combo?`Load reasoning ${code} ${letter}`:`Load human notes ${code}`:undefined} onClick={()=>void load()}>{error?'Retry':cursor===undefined?combo?'Load reasoning':'Load human notes':'Load more'}</button>}
 </section>;
}

/** Reasoning roll-up: collapsed accordion per code (Human count + combo snippets). Panels mount, and fetch, only when a code is expanded. */
export function ReasoningRollup({codes,human,rationaleCounts,combos,letter,api,runId,selected}:{codes:string[];human:CompareDeepDive['counts']['human'];rationaleCounts:CompareDeepDive['rationale_counts'];combos:string[];letter:(key:string)=>string;api:Api;runId:string;selected:string[]}) {
 // Loaded pages survive collapsing a code; the cache is dropped when the selected combos change.
 const selectedKey=selected.join(',');
 // eslint-disable-next-line react-hooks/exhaustive-deps
 const cache=useMemo<Cache>(()=>new Map(),[selectedKey]);
 return <section className="deep-reasoning"><h3 className="deep-section-title">Reasoning roll-up</h3>
  <Disclosure label="Show reasoning roll-up">
   <Note>Snippets load when a code is opened, up to 50 per page. Empty saved reasoning is shown as withheld.</Note>
   {codes.map(code=><Disclosure key={code} label={code}><div className="deep-reasoning-columns"><section aria-label={`${code} Human`}><h5>Human</h5><p>Count: {human?.[code]?.value??unavailable(human?.[code]?.na)} · n={human?.[code]?.n??0}</p><ReasoningPanel key={`h-${selected.join(',')}`} code={code} letter="Human" count={undefined} api={api} runId={runId} selected={selected} cache={cache}/></section>{combos.map(key=><ReasoningPanel key={`${key}-${selected.join(',')}`} code={code} combo={key} letter={letter(key)} count={rationaleCounts[code]?.[key]} api={api} runId={runId} selected={selected} cache={cache}/>)}</div></Disclosure>)}
  </Disclosure>
 </section>;
}
