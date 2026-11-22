import { useUsage } from "./useUsage";
import { usageLeftText, type PeriodName, type UsageKind } from "./usage";

/** "3 of 5 left today" for one kind and period; nothing until usage loads. */
export function UsageLeft({ kind, period }: { kind: UsageKind; period: PeriodName }) {
  const { data } = useUsage();
  return data ? <span>{usageLeftText(data[kind][period])}</span> : null;
}
