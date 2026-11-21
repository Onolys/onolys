/** Usage helpers (SP11 R9): pure functions over the `GET /usage` shape. */
import type { components } from "../../api/schema";
import { formatResetTime } from "../../lib/format";

export type Usage = components["schemas"]["Usage"];
export type Period = components["schemas"]["Period"];
export type UsageKind = keyof Usage;
export type PeriodName = "day" | "month";

/** What is left in a period, never below zero. */
export function remaining(period: Period): number {
  return Math.max(0, period.cap - period.used);
}

export interface Blocking {
  name: PeriodName;
  period: Period;
}

/** The exhausted period for a kind: month if exhausted, else day, else null (also null until usage loads). */
export function blockingPeriod(usage: Usage | undefined, kind: UsageKind): Blocking | null {
  if (!usage) return null;
  const k = usage[kind];
  if (remaining(k.month) === 0) return { name: "month", period: k.month };
  if (remaining(k.day) === 0) return { name: "day", period: k.day };
  return null;
}

/** "3 of 5 left today" / "12 of 30 left this month". */
export function usageLeftText(period: Period, name: PeriodName): string {
  return `${remaining(period)} of ${period.cap} left ${name === "day" ? "today" : "this month"}`;
}

/** When the blocking period resets, for display: a time for the day cap, a date for the month cap. */
export function formatBlockingReset(b: Blocking | null): string | undefined {
  if (!b) return undefined;
  if (b.name === "day") return formatResetTime(b.period.resets_at);
  const d = new Date(b.period.resets_at);
  return Number.isNaN(d.getTime()) ? undefined : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** The eval error code that matches a blocking period. */
export function evalCapCode(b: Blocking): "daily_cap_reached" | "monthly_cap_reached" {
  return b.name === "month" ? "monthly_cap_reached" : "daily_cap_reached";
}
