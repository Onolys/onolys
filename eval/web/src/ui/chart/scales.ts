import { scaleBand, scaleLinear } from "@visx/scale";

/** Scores are rated 1-5 everywhere in the eval UI. */
export const SCORE_DOMAIN: [number, number] = [1, 5];
export const SCORE_TICKS = [1, 2, 3, 4, 5];

/** Linear 1-5 scale onto [start, end]. Pass start > end for a vertical axis (1 at the bottom). */
export function scoreScale(start: number, end: number) {
  return scaleLinear<number>({ domain: SCORE_DOMAIN, range: [start, end] });
}

export const clampScore = (v: number) => Math.min(SCORE_DOMAIN[1], Math.max(SCORE_DOMAIN[0], v));

export function linearScale({ domain, range, nice = false }: { domain: [number, number]; range: [number, number]; nice?: boolean }) {
  return scaleLinear<number>({ domain, range, nice });
}

export function bandScale({ domain, range, padding = 0.2 }: { domain: string[]; range: [number, number]; padding?: number }) {
  return scaleBand<string>({ domain, range, padding });
}
