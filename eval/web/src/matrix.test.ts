import { describe, expect, it } from 'vitest';
import fixture from '../../fixtures/selection_cases.json';
import type { Selection } from './api';
import { comboKey, countText, planCount, tooLargeMessage, validateSelection, MAX_UNITS } from './matrix';

type Case = { name: string; selection: Selection; engines: string[]; sessions: number; repeats: number; expect: { error?: string; combos?: string[]; dropped?: string[]; units?: number } };

describe('client selection planning matches the shared server fixture', () => {
  it.each(fixture.cases as Case[])('$name', c => {
    const result = validateSelection(fixture.models, c.selection, c.engines.some(e => e !== 'human'));
    const plan = result.error === undefined ? planCount(c.sessions, c.engines, result.combos.length, c.repeats) : undefined;
    if (result.error === undefined && plan && plan.units > MAX_UNITS) { expect(tooLargeMessage(plan.units)).toBe(c.expect.error); return; }
    if (c.expect.error) { expect(result.error).toBe(c.expect.error); return; }
    expect(result.error).toBeUndefined();
    if (result.error !== undefined) return;
    expect(result.combos.map(comboKey)).toEqual(c.expect.combos);
    expect(result.dropped.map(comboKey)).toEqual(c.expect.dropped);
    expect(plan?.units).toBe(c.expect.units);
  });
  it('formats the count text', () => {
    expect(countText(planCount(2, ['human', 'miti', 'oneshot:miti'], 2, 3))).toBe('26 units = 2 sessions x (1 human + 2 engines x 2 combos x 3 repeats)');
  });
});
