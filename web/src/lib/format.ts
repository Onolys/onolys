/** Elapsed milliseconds as `m:ss`. */
export function formatElapsed(ms: number): string {
  if (!Number.isFinite(ms)) return "0:00";
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** A reset timestamp as a short local clock time with its time zone ("9:00 AM PST"); undefined when unparseable. */
export function formatResetTime(iso: string | undefined): string | undefined {
  if (!iso) return undefined;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return undefined;
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", timeZoneName: "short" });
}
