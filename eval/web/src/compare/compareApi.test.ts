import { expect, it, vi } from 'vitest';
import { createEvalApi, ApiError } from '../api';
import { ComparePayloadError } from './compareApi';
import overview from './fixtures/overview.json';
import deep from './fixtures/deepDive.json';
import analysis from './fixtures/analysis.json';
import reasoning from './fixtures/reasoning.json';
import lines from './fixtures/lines.json';
import turn from './fixtures/turn.json';
it('loads all real SP06 projections through the authenticated request with opaque filters', async () => {
 const fetcher=vi.fn(); const api=createEvalApi('https://eval/',fetcher); const signal=new AbortController().signal;
 for (const [call,payload,suffix] of [
  [() => api.compareOverview('r/1',{combos:['miti|model/tier/effort']},signal),overview,'overview'],
  [() => api.compareDeepDive('r/1',{},signal),deep,'deep-dive'],
  [() => api.compareAnalysis('r/1',{},signal),analysis,'analysis'],
  [() => api.compareReasoning('r/1',{code:'question',combo:'opaque',cursor:'next'},signal),reasoning,'reasoning'],
  [() => api.compareLines('r/1','s/1',{},signal),lines,'sessions/s%2F1/lines'],
  [() => api.compareTurn('r/1','s/1','t/1',{},signal),turn,'sessions/s%2F1/lines/t%2F1'],
 ] as const) {
  fetcher.mockResolvedValueOnce(new Response(JSON.stringify(payload)));
  expect(await call()).toEqual(payload);
  const [url,init]=fetcher.mock.calls.at(-1)!; expect(String(url)).toContain(`/v1/eval-runs/r%2F1/compare/${suffix}`); expect(init.signal).toBe(signal);
 }
 const params=new URL(String(fetcher.mock.calls[0][0])).searchParams;
 expect(params.get('combos')).toBe('miti|model/tier/effort');
 expect(overview.heatmap.rows).toHaveLength(16);
 expect(overview.leaderboard[0]).toHaveProperty('globals_within_1');
});
it.each([null, {}, { ...overview, leaderboard: {} }, { ...overview, heatmap: null }, { ...overview, combos: {} }])('rejects malformed overview %j at the boundary', async payload => {
 const api=createEvalApi('',vi.fn().mockResolvedValue(new Response(JSON.stringify(payload))));
 await expect(api.compareOverview('r')).rejects.toBeInstanceOf(ComparePayloadError);
});
it.each([[404,'not_found'],[409,'transcript_changed'],[409,'no_completed_runs'],[409,'not_finished']])('retains HTTP %s and error code %s',async (status,code)=>{
 const api=createEvalApi('',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:{code,message:'saved message'}}),{status:Number(status)})));
 await expect(api.compareOverview('r')).rejects.toMatchObject({name:'ApiError',status,code,message:'saved message'});
 try {await api.compareOverview('r');} catch(error) {expect(error).toBeInstanceOf(ApiError);}
});
it('aborts only the supplied request and preserves AbortError',async()=>{
 const fetcher=vi.fn((_url,init)=>new Promise((_resolve,reject)=>init.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))));
 const api=createEvalApi('',fetcher as unknown as typeof fetch); const first=new AbortController(), second=new AbortController();
 const a=api.compareOverview('r',{},first.signal); const b=api.compareAnalysis('r',{},second.signal); const checked=expect(a).rejects.toMatchObject({name:'AbortError'});
 first.abort(); await checked; expect(second.signal.aborted).toBe(false); const checkedB=expect(b).rejects.toMatchObject({name:'AbortError'}); second.abort(); await checkedB;
});
it.each(['deep','analysis','reasoning','lines','turn'] as const)('rejects malformed %s containers before rendering', async kind => {
 const payloads={deep:{...deep,globals:[]},analysis:{...analysis,frontier:[]},reasoning:{...reasoning,groups:{}},lines:{...lines,turns:{}},turn:{...turn,combos:[]}};
 const api=createEvalApi('',vi.fn().mockResolvedValue(new Response(JSON.stringify(payloads[kind]))));
 const calls={deep:()=>api.compareDeepDive('r'),analysis:()=>api.compareAnalysis('r'),reasoning:()=>api.compareReasoning('r'),lines:()=>api.compareLines('r','s'),turn:()=>api.compareTurn('r','s','t')};
 await expect(calls[kind]()).rejects.toBeInstanceOf(ComparePayloadError);
});
it('retains normalized backend error envelopes too',async()=>{
 const api=createEvalApi('',vi.fn().mockResolvedValue(new Response(JSON.stringify({error:{code:'not_found',message:'Run missing'}}),{status:404})));
 await expect(api.compareOverview('r')).rejects.toMatchObject({status:404,code:'not_found',message:'Run missing'});
});
it('loads matching sessions once using opaque combo and both confusion filters',async()=>{
 const fetcher=vi.fn().mockResolvedValue(new Response(JSON.stringify({session_ids:['synthetic-s01','synthetic-s02']})));
 const api=createEvalApi('https://eval',fetcher),signal=new AbortController().signal;
 expect(await api.compareLineMatches('r/1',{combos:['miti|m/t/e','other'],combo:'miti|m/t/e',code:'sr',metric:'cr'},signal)).toEqual({session_ids:['synthetic-s01','synthetic-s02']});
 expect(fetcher).toHaveBeenCalledTimes(1);const [url,init]=fetcher.mock.calls[0];const parsed=new URL(String(url));
 expect(parsed.pathname).toBe('/v1/eval-runs/r%2F1/compare/line-matches');expect(parsed.searchParams.get('combos')).toBe('miti|m/t/e,other');expect(parsed.searchParams.get('combo')).toBe('miti|m/t/e');expect(parsed.searchParams.get('code')).toBe('sr');expect(parsed.searchParams.get('metric')).toBe('cr');expect(init.signal).toBe(signal);
});
it.each([null,{}, {session_ids:[1]}, {session_ids:'bad'}])('rejects malformed matching session payload %j',async payload=>{
 const api=createEvalApi('',vi.fn().mockResolvedValue(new Response(JSON.stringify(payload))));
 await expect(api.compareLineMatches('r',{combo:'c',code:'multi',metric:'multi'})).rejects.toBeInstanceOf(ComparePayloadError);
});
it('scopes global reasoning by session and kind with the existing cursor',async()=>{
 const fetcher=vi.fn().mockResolvedValue(new Response(JSON.stringify(reasoning))),api=createEvalApi('https://eval',fetcher),signal=new AbortController().signal;
 await api.compareReasoning('r',{session:'upload/1',kind:'global',combos:['opaque'],cursor:'next'},signal);
 const query=new URL(String(fetcher.mock.calls[0][0])).searchParams;
 expect(query.get('session')).toBe('upload/1');expect(query.get('kind')).toBe('global');expect(query.get('cursor')).toBe('next');expect(fetcher.mock.calls[0][1].signal).toBe(signal);
});
it.each([{session_id:'s',matched_lines:'5'},{session_id:1,matched_lines:0}])('rejects malformed line session choices %j',async row=>{
 const api=createEvalApi('',vi.fn().mockResolvedValue(new Response(JSON.stringify({...overview,header:{...overview.header,line_sessions:[row]}}))));
 await expect(api.compareOverview('r')).rejects.toBeInstanceOf(ComparePayloadError);
});
