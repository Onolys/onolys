import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@onolys/ui";
import { useUsage } from "./useUsage";
import { remaining, usageLeftText, type Period, type UsageKind } from "./usage";

/** Colour by remaining share of the daily cap: <25% destructive, 25% to <50% warning, else success. */
export function usageTone(left: number, cap: number): string {
  const pct = cap > 0 ? left / cap : 0;
  if (pct < 0.25) return "text-destructive";
  if (pct < 0.5) return "text-warning";
  return "text-success";
}

/** Compact "x/y" (remaining / daily limit), focusable, with a tooltip on hover and focus. */
export function UsageCountView({ period }: { period: Period }) {
  const left = remaining(period);
  const text = usageLeftText(period);
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button type="button" aria-label={text} className="cursor-default rounded-sm bg-transparent p-0 text-sm font-semibold tabular-nums focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
            <span className={usageTone(left, period.cap)}>
              {left}/{period.cap}
            </span>
          </button>
        </TooltipTrigger>
        <TooltipContent>{text}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/** Remaining daily allowance for one kind; nothing until usage loads. */
export function UsageCount({ kind }: { kind: UsageKind }) {
  const { data } = useUsage();
  return data ? <UsageCountView period={data[kind].day} /> : null;
}
