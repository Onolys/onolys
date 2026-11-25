import type { EvalApi, RunDetail } from '../api';
import type { CompareCombo, CompareOverview } from './compareApi';
import type { CompareUrlState } from './compareUrl';
import type { CompareNavigate } from './CompareLink';
export interface ComboLegendEntry { letter:string; label:string; combo:CompareCombo }
/** Tab components render their projection; shell owns fetch, cache and URL navigation. */
export interface CompareTabProps<T> {
 data:T;
 overview:CompareOverview;
 run?:RunDetail;
 state:CompareUrlState;
 navigate:CompareNavigate;
 legend:ComboLegendEntry[];
 api:EvalApi;
 runId:string;
}
