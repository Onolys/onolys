import { useEffect, useRef, useState } from 'react';
import type { CompareLines, CompareTurn, ModelLane } from './compareApi';
import type { CompareTabProps } from './compareTypes';
import { LineFilters } from './line/LineFilters';
import { LaneTable } from './line/LaneTable';
import { LinePopup } from './line/LinePopup';
import { SessionRatings } from './line/SessionRatings';
import './lineView.css';
const category=(value:string[])=>value.length>1?'multi':value[0]??'none';
const same=(a:string[],b:string[])=>a.length===b.length&&a.every(code=>b.includes(code));
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
 const laneUnavailable=(key:string,turnId:string)=>{
  const item=lane(key);
  if(item?.missing)return item.missing;
  if(!item||item.n===0||item.repeats===0)return data.excluded.find(row=>row.session_id===data.session_id&&row.combo_key===key)?.reason??'no completed runs';
  return item.turns[turnId]?.length?null:'no line-level output for this turn';
 };
 if(!data.has_human)return <p>no human reference</p>;
 if(data.missing==='human'||data.missing==='both'||data.gold.utterance_codes===null)return <p>no line-level output (human)</p>;
 const human=data.lanes.human??{};
 const laneDisagrees=(key:string,turnId:string)=>human[turnId]!==undefined&&!laneUnavailable(key,turnId)&&Boolean(lane(key)?.turns[turnId]?.some(row=>!same(row,human[turnId])));
 const isDisagreement=(turnId:string)=>state.combo?laneDisagrees(state.combo,turnId):data.disagreement[turnId];
 const turns=data.turns.filter(turn=>{
  if(state.only==='disagree'&&!isDisagreement(turn.id))return false;
  if(state.code==='multi'&&state.metric==='multi')return human[turn.id]!==undefined&&([human[turn.id],...(state.combo?lane(state.combo)?.turns[turn.id]??[]:[])].some(row=>category(row)==='multi'));
  if(state.code&&(human[turn.id]===undefined||category(human[turn.id])!==state.code))return false;
  if(state.metric){const lanes=state.combo?[state.combo]:selected;if(!lanes.some(key=>lane(key)?.turns[turn.id]?.some(row=>category(row)===state.metric)))return false;}
  return true;
 });
 const active=popup?.key===popupKey?popup:undefined;
 const differingCount=data.turns.filter(turn=>isDisagreement(turn.id)).length;
 return <section className="line-view"><h2>Line view</h2><LineFilters state={state} sessionId={data.session_id} sessions={overview.header.line_sessions??[{session_id:data.session_id,matched_lines:null}]} selected={selected} legend={legend} letter={letter} differing={differingCount} change={change}/>
 <LaneTable turns={turns} selected={selected} human={human} lane={lane} letter={letter} unavailable={laneUnavailable} disagrees={laneDisagrees} isDisagreement={id=>Boolean(isDisagreement(id))} expanded={expanded} toggle={id=>setExpanded(old=>({...old,[id]:!old[id]}))} inspect={(id,trigger)=>{returnFocus.current=trigger;navigate({...state,view:'compare',run:runId,tab:'lines',turn:id});}} setTrigger={(id,node)=>{triggers.current[id]=node;}}/>{data.dataset_notes.map((note,i)=><p key={i} className="line-verbatim">{note}</p>)}
 <SessionRatings key={`${data.session_id}-${keys}`} data={data} api={api} runId={runId} selected={selected} letter={letter}/>
 <LinePopup turnId={state.turn} selected={selected} letter={letter} loaded={active} unavailable={laneUnavailable} retry={()=>setAttempt(n=>n+1)} onClose={()=>navigate({...state,turn:undefined})} returnFocus={returnFocus}/>
 </section>;
}
