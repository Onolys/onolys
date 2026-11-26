// @vitest-environment jsdom
import { readFileSync } from 'node:fs';
import { cleanup, render } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createEvalApi } from '../api';
import { Overview } from './Overview';
import { DeepDive } from './DeepDive';
import { MoreAnalysis } from './MoreAnalysis';
import { LineView } from './LineView';
import type { CompareOverview, CompareDeepDive, CompareAnalysis, CompareLines } from './compareApi';
import overview from './fixtures/overview.json';
import deep from './fixtures/deepDive.json';
import analysis from './fixtures/analysis.json';
import lines from './fixtures/lines.json';

afterEach(cleanup);
const css = (file: string) => readFileSync(new URL(file, import.meta.url), 'utf8');
const styles = ['compare.css', 'overview.css', 'metricHeatmap.css', 'leaderboard.css', 'deepDive.css', 'moreAnalysis.css', 'lineView.css'].map(css).join('\n');
const sheet = document.createElement('style');
sheet.textContent = styles;
document.head.append(sheet);

// jsdom does not lay out pages. Verify the actual CSS breakpoint contract and
// semantic scroll/chart structure; the owner's browser check verifies pixels.
it.each([320, 768, 1280])('retains accessible chart/table structure at the %ipx breakpoint', width => {
 Object.defineProperty(window, 'innerWidth', { value: width, configurable: true });
 const data = overview as CompareOverview;
 const props = {
  overview: data, state: { view: 'compare' as const, run: 'r1' }, runId: 'r1', navigate: vi.fn(),
  api: { ...createEvalApi('', vi.fn()), compareReasoning: vi.fn().mockResolvedValue({ groups: [], next_cursor: null }) },
  legend: data.combos.map((combo, index) => ({ combo, letter: String.fromCharCode(65 + index), label: combo.combo_key })),
 };
 const view = render(<>
  <Overview {...props} data={data}/>
  <DeepDive {...props} data={deep as CompareDeepDive}/>
  <MoreAnalysis {...props} data={analysis as CompareAnalysis}/>
  <LineView {...props} data={lines as CompareLines}/>
 </>);
 // Every remaining scroll region (Overview/MoreAnalysis/LineView) must stay named and keyboard-focusable.
 view.container.querySelectorAll('[role="region"]').forEach(region => {
  expect(region.getAttribute('aria-label')).toBeTruthy();
  expect(region.getAttribute('tabindex')).toBe('0');
 });
 // Deep dive cards use the shared ui ChartFrame: titled section, one-sentence caption, table twin collapsed behind "Show data".
 const deepRoot = view.container.querySelector('.deep-dive') as HTMLElement;
 const cards = deepRoot.querySelectorAll('.ui-chart-frame');
 expect(cards.length).toBeGreaterThanOrEqual(8); // 4 globals + 4+ counts/PRF/confusion/miss cards
 cards.forEach(card => {
  expect(card.querySelector('h3')?.id).toBe(card.getAttribute('aria-labelledby'));
  expect(card.querySelector('.ui-chart-caption')?.textContent?.trim()).toBeTruthy();
  const twin = card.querySelector('.ui-disclosure-toggle');
  expect(twin?.textContent).toMatch(/Show data/);
  expect(twin?.getAttribute('aria-expanded')).toBe('false');
  expect(card.querySelector('table')).toBeNull(); // twin not rendered until opened (no hidden wide tables)
 });
 // Dot plots scale by viewBox: no fixed pixel width/height attributes, so they can never force horizontal scroll.
 const svgs = deepRoot.querySelectorAll('svg.deep-dot-svg');
 expect(svgs.length).toBe(4);
 svgs.forEach(svg => {
  expect(svg.getAttribute('viewBox')).toMatch(/^0 0 \d+(\.\d+)? \d+(\.\d+)?$/);
  expect(svg.hasAttribute('width')).toBe(false);
  expect(svg.hasAttribute('height')).toBe(false);
 });
 expect(styles).toMatch(/\.deep-dot-svg\s*\{[^}]*width:\s*100%/);
 // Cards stack to one column at the breakpoint.
 expect(styles).toMatch(/@media\(max-width:760px\)[^]*\.deep-grid\s*\{\s*grid-template-columns:\s*minmax\(0,1fr\)/);
 expect(styles).not.toMatch(/overflow-x\s*:\s*(auto|scroll)/);
 // Heatmap is collapsed by default (opened by toggle); the leaderboard is a DataTable with no scroll region.
 expect(view.container.querySelector('.overview-heatmap')).toBeNull();
 const media = [...sheet.sheet!.cssRules].filter((rule): rule is CSSMediaRule => rule.type === CSSRule.MEDIA_RULE);
 expect(media.some(rule => rule.conditionText.replaceAll(' ', '') === '(max-width:760px)')).toBe(true);
 expect(width <= 760).toBe(width === 320);
 // Line view: fixed-layout lane table that wraps (no scroll region), stacked cards at <=760px, no pixel widths.
 const lineView = view.container.querySelector('.line-view') as HTMLElement;
 expect(lineView.querySelector('.line-lanes table')).toBeTruthy();
 expect(lineView.querySelector('.line-lanes [role="region"], .line-lanes .table-scroll')).toBeNull();
 expect(lineView.querySelector('.line-lanes td.line-verbatim, .line-lanes [data-transcript]')).toBeTruthy();
 const lineCss = css('lineView.css');
 expect(lineCss).toMatch(/\.line-view table\s*\{[^}]*table-layout:\s*fixed/);
 expect(lineCss).toMatch(/\.line-view table\s*\{[^}]*width:\s*100%/);
 expect(lineCss).toMatch(/@media \(max-width: 760px\)\s*\{[\s\S]*\.line-view tr[^{]*\{[^}]*display:\s*block/);
 expect(lineCss).toMatch(/td\[data-label\]::before/);
 expect(lineCss).not.toMatch(/\.line-view thead th:nth-child/); // column widths are scoped to the lane table only
 expect(lineCss).toMatch(/\.line-view \.line-lanes thead th:nth-child\(1\)/);
 expect(lineView.querySelectorAll('.line-lanes thead th .ui-combo-tag').length).toBeGreaterThan(0);
 expect(lineView.querySelector('.line-lanes td[data-label^="Combo "]')).toBeTruthy();
 // Turns/Words toggle must reset the global white-on-primary button colour so the unpressed segment is readable.
 expect(css('charts/errorVsLength.css')).toMatch(/\.evl-toggle button\s*\{[^}]*color:\s*var\(--foreground\)[^}]*margin:\s*0[^}]*min-height:\s*0/);
 expect(lineCss).not.toMatch(/overflow(-x)?\s*:\s*(auto|scroll)/);
 // Wide content wraps inside its container, not a fixed pixel width on a page.
 expect(styles).not.toMatch(/(?:^|[;{])\s*width:\s*\d+px/);
 expect(view.container.querySelector('[style*="width: 320px"], [style*="width: 768px"], [style*="width: 1280px"]')).toBeNull();
});
