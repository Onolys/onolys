/** Usage helpers: pure functions over the `GET /usage` shape. */
import type { components } from "../../api/schema";
import { formatResetTime } from "@onolys/common";

export type Usage = components["schemas"]["Usage"];
export type Period = components["schemas"]["Period"];
export type UsageKind = keyof Usage;
export type PeriodName = "day";

/** What is left in a period, never below zero. */
export function remaining(period: Period): number {
  return Math.max(0, period.cap - period.used);
}

export interface Blocking {
  name: PeriodName;
  period: Period;
}

/** The exhausted period for a kind (the daily cap), else null (also null until usage loads). */
export function blockingPeriod(usage: Usage | undefined, kind: UsageKind): Blocking | null {
  if (!usage) return null;
  const k = usage[kind];
  if (remaining(k.day) === 0) return { name: "day", period: k.day };
  return null;
}

/** "3 of 5 left today". */
export function usageLeftText(period: Period): string {
  return `${remaining(period)} of ${period.cap} left today`;
}

/** When the daily cap resets, for display (a time of day). */
export function formatBlockingReset(b: Blocking | null): string | undefined {
  return b ? formatResetTime(b.period.resets_at) : undefined;
}
