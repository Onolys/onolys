import { expect, it } from 'vitest';
import { buildCompareUrl, parseCompareUrl } from './compareUrl';
it('round trips all drill-down state and opaque combo keys', () => {
 const state = { run: 'run/1', view: 'compare' as const, tab: 'lines' as const, combos: ['miti|model/standard/high', 'oneshot|model/flex/low'], combo: 'miti|model/standard/high', code: 'question', metric: 'empathy', session: 's/1', turn: '0', only: 'disagree' };
 const url = buildCompareUrl(state, '?other=keep');
 expect(parseCompareUrl(url)).toEqual(state);
 expect(new URLSearchParams(url).get('other')).toBe('keep');
});
it('accepts a single combo and uses safe defaults for unknown views and tabs', () => {
 expect(parseCompareUrl('?run=r&view=compare&combo=miti%7Cm%2Ft%2Fe&tab=bad')).toMatchObject({run:'r', view:'compare', tab:'overview', combos:['miti|m/t/e'], combo:'miti|m/t/e'});
 expect(parseCompareUrl('?run=r')).toMatchObject({view:'run'});
 expect(parseCompareUrl('?view=history')).toMatchObject({view:'history'});
 expect(parseCompareUrl('?view=bad')).toMatchObject({view:'new'});
});
it('clears compare parameters when leaving for a run and deduplicates selections', () => {
 const url = buildCompareUrl({run:'r',view:'run'}, '?view=compare&tab=deep&combos=a,b&code=q&other=keep');
 expect(url).toBe('?other=keep&run=r');
 expect(parseCompareUrl('?run=r&view=compare&combos=a,a,b').combos).toEqual(['a','b']);
});
