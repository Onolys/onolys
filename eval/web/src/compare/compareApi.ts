import type { CodedSpan, RunStatus } from '../api';
/** Relative to the existing authenticated /v1 request transport. */
export const COMPARE_PREFIX = '/eval-runs';
export type NA = { reason: string } | null;
export interface Observed { min: number | null; max: number | null; n: number }
export interface CompareCell {
 value: number | null; off: number | null; bias: number | null; n: number; of: number; repeats: number;
 within_tolerance: boolean | null; best: boolean; na: NA; observed?: Observed;
 buckets?: {same:number;off1:number;off2plus:number}; within_1?: number; codes_labeled?: number; codes_total?: number;
}
export interface ValueCell {value:number|null;n:number;na:NA;observed?:Observed}
export interface QualityCell extends ValueCell {repeats:number;best:boolean}
export interface CompareCoverage {
 eval_status: RunStatus; cancelled_at: string | null; runs_done: number; runs_total: number; runs_skipped: number;
 skipped_providers: {provider:string;after_failures:number}[];
}
export interface CompareCombo {combo_key:string;engine:string;model:string|null;tier:string|null;effort:string|null}
export interface CompareCommon {
 eval_run_id:string;has_human:boolean;combos:CompareCombo[];coverage:CompareCoverage;
 excluded:{session_id:string;combo_key:string|null;reason:string;repeat?:number;metric?:string}[];
}
export interface Operations {
 time:{mean_seconds:number|null;n:number;retried_runs:number};cost:{total_usd:number|null;per_run_usd:number|null;n:number;na:NA};failures:{code:string;count:number}[];
}
export interface Verdict {text:string;claims:{metric:string;combo:string;value:number;n:number}[]}
export type MetricCells = Record<string,Record<string,CompareCell>>;
export interface CompareOverview extends CompareCommon {
 header:{name:string|null;dataset_id:string|null;sessions:number;repeats:number;label_coverage:{counts:string[];globals:string[];line_labels:boolean}|null;coverage:CompareCoverage};
 count_error:Record<string,CompareCell>;verdict:Verdict[];
 leaderboard:(CompareCell & Operations & {combo_key:string;globals_within_1:QualityCell;line_accuracy:QualityCell;macro_f1:QualityCell})[];
 heatmap:{rows:{id:string;kind:'count'|'global'|'ratio'|'total'}[];human:Record<string,Observed & {values:{session_id:string;value:number}[]}>;cells:MetricCells};
 cohorts:Record<string,{paired:number;of:number}>;footnotes:string[];
}
export interface LineMetrics {
 missing:string|null;codes_labeled:string[];dataset_notes:string[];
 combos:Record<string,{lane:string|null;n:number;repeats:number;aligned:number;per_code:Record<string,{p:number|null;r:number|null;f1:number|null}>;macro_f1:number|null;line_accuracy:number|null;confusion:Record<string,Record<string,number>>;multi:number}>;
}
export interface CompareDeepDive extends CompareCommon {
 cohorts?:Record<string,{paired:number;of:number}>;
 globals:{cells:MetricCells;dots:{session_id:string;combo_key:string;metric:string;human:number|null;values:number[];n:number;repeats:number}[]};
 counts:{human?:Record<string,ValueCell & {min:number|null;max:number|null}>;cells:MetricCells;totals:{session_id:string;combo_key:string;human:Record<string,number>;values:Record<string,number>[];n:number;repeats:number}[];bias_pct:Record<string,Record<string,ValueCell>>};
 lines:LineMetrics;rationale_counts:Record<string,Record<string,number>>;
}
export interface FrontierPoint {combo_key:string;count_error:number;n:number;cost_per_run_usd:number;cost_n:number}
export interface CompareAnalysis extends CompareCommon {
 count_error:Record<string,Partial<CompareCell> & Pick<CompareCell,'off'|'n'|'na'>>;skipped_combos:string[];verdict:Verdict[];
 frontier:{points:FrontierPoint[];dominated:FrontierPoint[];unpriced:{combo_key:string;count_error:number;n:number;cost_per_run_usd:null;na:NA}[];unavailable:{combo_key:string;n:number;na:NA}[]};
 baseline:ValueCell;reliability:Record<string,{levels:Record<string,ValueCell>;repeat_agreement:{globals:ValueCell & {agree:number};lines:ValueCell & {agree:number}};na:NA;failures:Operations['failures'];time:Operations['time']}>;
 head_to_head:{a:string;b:string;a_closer:number;b_closer:number;ties:number;n:number;na:NA}[];
 grid:{session_id:string;cells:Record<string,{off:number|null;n:number;repeats:number;codes_labeled:number;observed:Observed;na:NA}>}[];
 error_vs_length:{session_id:string;combo_key:string;off:number;turns:number;words:number;n:number;repeats:number}[];
}
export interface Snippet {session_id:string;combo_key:string;repeat:number;rationale:string;withheld:boolean;turn_id?:string;quote?:string|null;quote_verified?:boolean;evidence?:{turn_id:string;quote:string}[]}
export interface CompareReasoning extends CompareCommon {groups:{code:string;snippets:Snippet[];human_notes?:{session_id:string;turn_id:string;note:string}[]}[];next_cursor:string|null}
export interface TranscriptTurn {id:string;speaker:string;is_clinician:boolean;text:string;start_ms?:number|null;end_ms?:number|null}
export interface ModelLane {missing:string|null;n:number;repeats:number;turns:Record<string,string[][]>}
export interface CompareLines extends CompareCommon {
 session_id:string;turns:TranscriptTurn[];gold:{coded_span?:CodedSpan|null;counts:Record<string,number>;globals:Record<string,number>;quality_label:string|null;utterance_codes:{turn_id:string;codes:string[];note:string|null}[]|null};missing:string|null;
 // The human lane is a turn-to-code map; model lanes contain repeat code sets.
 lanes:{human?:Record<string,string[]>} & Record<string,ModelLane|Record<string,string[]>|undefined>;
 disagreement:Record<string,boolean>;globals:{human:Record<string,number>;combos:Record<string,Record<string,number>[]>};dataset_notes:string[];
}
/** Unlike the other projections, the popup's `combos` is a keyed lane map. */
export interface CompareTurn extends Omit<CompareCommon,'combos'> {
 session_id:string;turn_id:string;text:string;human:{codes:string[];note:string|null}|null;missing:string|null;
 combos:Record<string,{missing:string|null;codes:string[][];rationales:Snippet[];agree:{k:number;r:number}|null}>;
}
export interface CompareOptions {combos?:string[];code?:string;combo?:string;metric?:string;cursor?:string}
export interface CompareApi {
 compareLineMatches(runId:string,options?:CompareOptions,signal?:AbortSignal):Promise<{session_ids:string[]}>;
 compareOverview(runId:string,options?:CompareOptions,signal?:AbortSignal):Promise<CompareOverview>;
 compareDeepDive(runId:string,options?:CompareOptions,signal?:AbortSignal):Promise<CompareDeepDive>;
 compareAnalysis(runId:string,options?:CompareOptions,signal?:AbortSignal):Promise<CompareAnalysis>;
 compareReasoning(runId:string,options?:CompareOptions,signal?:AbortSignal):Promise<CompareReasoning>;
 compareLines(runId:string,sessionId:string,options?:CompareOptions,signal?:AbortSignal):Promise<CompareLines>;
 compareTurn(runId:string,sessionId:string,turnId:string,options?:CompareOptions,signal?:AbortSignal):Promise<CompareTurn>;
}
export class ComparePayloadError extends Error {constructor(){super('The server returned an invalid compare response. Please retry.');this.name='ComparePayloadError';}}
const object = (v:unknown): v is Record<string,unknown> => v !== null && typeof v === 'object' && !Array.isArray(v);
/** Boundary checks deliberately inspect containers only; metric semantics stay on the server. */
function checked<T>(value:unknown, kind:'overview'|'deep'|'analysis'|'reasoning'|'lines'|'turn'):T {
 if (!object(value) || typeof value.eval_run_id!=='string' || typeof value.has_human!=='boolean' || !object(value.coverage) || !Array.isArray(value.excluded) || (kind==='turn' ? !object(value.combos) : !Array.isArray(value.combos))) throw new ComparePayloadError();
 const records:Record<typeof kind,string[]>={overview:['header','count_error','heatmap','cohorts'],deep:['globals','counts','lines','rationale_counts'],analysis:['frontier','baseline','reliability'],reasoning:[],lines:['gold','lanes','globals','disagreement'],turn:[]};
 const arrays:Record<typeof kind,string[]>={overview:['leaderboard','verdict','footnotes'],deep:[],analysis:['grid','head_to_head','error_vs_length'],reasoning:['groups'],lines:['turns','dataset_notes'],turn:[]};
 if(records[kind].some(k=>!object(value[k])) || arrays[kind].some(k=>!Array.isArray(value[k]))) throw new ComparePayloadError();
 if(kind==='reasoning' && value.next_cursor !== null && typeof value.next_cursor !== 'string') throw new ComparePayloadError();
 if((kind==='lines' || kind==='turn') && typeof value.session_id !== 'string') throw new ComparePayloadError();
 if(kind==='turn' && (typeof value.turn_id !== 'string' || typeof value.text !== 'string')) throw new ComparePayloadError();
 if(kind==='overview' && (!object(value.heatmap) || !Array.isArray(value.heatmap.rows) || !object(value.heatmap.cells) || !object(value.heatmap.human))) throw new ComparePayloadError();
 return value as T;
}
export function createCompareApi(request:<T>(path:string,init?:RequestInit)=>Promise<T>):CompareApi {
 const get = async <T>(run:string,path:string,kind:Parameters<typeof checked>[1],options:CompareOptions={},signal?:AbortSignal):Promise<T> => {
  const query=new URLSearchParams();if(options.combos?.length)query.set('combos',options.combos.join(','));
  for(const key of ['code','combo','metric','cursor'] as const)if(options[key])query.set(key,options[key]);
  return checked<T>(await request<unknown>(`${COMPARE_PREFIX}/${encodeURIComponent(run)}/compare/${path}${query.size?`?${query}`:''}`,{signal}),kind);
 };
 return {
  compareLineMatches:async(r,o={},signal)=>{
   const query=new URLSearchParams();if(o.combos?.length)query.set('combos',o.combos.join(','));
   for(const key of ['code','combo','metric'] as const)if(o[key])query.set(key,o[key]);
   const value=await request<unknown>(`${COMPARE_PREFIX}/${encodeURIComponent(r)}/compare/line-matches?${query}`,{signal});
   if(!object(value)||!Array.isArray(value.session_ids)||!value.session_ids.every(id=>typeof id==='string'))throw new ComparePayloadError();
   return {session_ids:value.session_ids as string[]};
  },
  compareOverview:(r,o,s)=>get(r,'overview','overview',o,s),compareDeepDive:(r,o,s)=>get(r,'deep-dive','deep',o,s),compareAnalysis:(r,o,s)=>get(r,'analysis','analysis',o,s),compareReasoning:(r,o,s)=>get(r,'reasoning','reasoning',o,s),
  compareLines:(r,sid,o,s)=>get(r,`sessions/${encodeURIComponent(sid)}/lines`,'lines',o,s),compareTurn:(r,sid,tid,o,s)=>get(r,`sessions/${encodeURIComponent(sid)}/lines/${encodeURIComponent(tid)}`,'turn',o,s),
 };
}
