import { describe, expect, it } from 'vitest';
import { sessionLabel } from './sessionLabel';

describe('sessionLabel', () => {
 it('maps an internal id to its dataset session name', () => expect(sessionLabel({ abc: 'high-001' }, 'abc')).toBe('high-001'));
 it('falls back to the id when labels are missing or incomplete', () => {
  expect(sessionLabel(undefined, 'abc')).toBe('abc');
  expect(sessionLabel({ other: 'x' }, 'abc')).toBe('abc');
 });
});
