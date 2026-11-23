import { Badge } from "@onolys/ui";
import { CODE_META, GROUP_CLASS, SHORT } from "./codeMeta";

/** Group colour from semantic tokens only; the chip text always names the code. */
const GROUP_TONE: Record<string, string> = {
  "c-info": "border-transparent bg-muted text-foreground",
  "c-qr": "border-transparent bg-muted text-primary",
  "c-mia": "border-transparent bg-score-good-bg text-score-good",
  "c-mina": "border-transparent bg-score-low-bg text-score-low",
};
export const PLAIN_CODE = "border-border bg-card text-foreground";

/** Short coloured chip for a code id (group colour from CODE_META). `data-code` is the semantic hook. */
export function CodeChip({ id }: { id: string }) {
  const meta = CODE_META[id];
  const group = GROUP_CLASS[meta?.group ?? ""] ?? "c-info";
  return (
    <Badge variant="outline" data-code="" data-group={group} className={`rounded font-mono text-xs font-semibold ${GROUP_TONE[group]}`}>
      {SHORT[id] ?? id}
    </Badge>
  );
}
