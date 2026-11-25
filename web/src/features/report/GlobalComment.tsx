import { Fragment, type ReactNode } from "react";
import type { GlobalEntry } from "../../api/report";
import type { components } from "../../api/schema";
import { evidenceUtterances } from "./codedRows";
import { UtteranceLink } from "./UtteranceLink";

type Turn = components["schemas"]["TranscriptTurnV1"];

/** Resolve IDs from the actual transcript order, never from a numeric ID suffix. */
export function GlobalComment({ global, turns }: { global: GlobalEntry; turns: readonly Turn[] | null }) {
  const evidence = turns ? evidenceUtterances(global, turns) : [];
  const allowed = new Set(evidence);
  const index = new Map((turns ?? []).map((t, i) => [t.id, i + 1]));
  const cited = new Set<number>();
  const reason = global.onolys?.reason ?? "";
  // Only legacy tN tokens are unambiguous inline references. Arbitrary IDs ("the", "3")
  // can also be ordinary prose; their verified evidence is linked after the sentence.
  const pattern = /(?<![\w-])t\d+(?![\w-])/g;
  const content: ReactNode[] = [];
  let start = 0;
  for (const match of reason.matchAll(pattern)) {
    const at = match.index;
    content.push(reason.slice(start, at));
    const n = index.get(match[0]);
    if (n !== undefined && allowed.has(n)) {
      content.push(<UtteranceLink key={`ref-${at}`} n={n} bracketed />);
      cited.add(n);
    } else {
      content.push("[reference unavailable]");
    }
    start = at + match[0].length;
  }
  content.push(reason.slice(start));
  const remaining = evidence.filter((n) => !cited.has(n));
  return (
    <>
      {content}
      {remaining.map((n) => (
        <Fragment key={n}>{" "}<UtteranceLink n={n} bracketed /></Fragment>
      ))}
    </>
  );
}
