import { UsageMeter } from "@onolys/ui";
import { useUsage } from "./useUsage";
import type { UsageKind } from "./usage";

/** Remaining daily allowance for one kind as a meter ("3 of 5 left today"); nothing until usage loads. */
export function UsageBar({ kind, label }: { kind: UsageKind; label: string }) {
  const { data } = useUsage();
  return data ? <UsageMeter label={label} used={data[kind].day.used} cap={data[kind].day.cap} periodLabel="today" /> : null;
}
