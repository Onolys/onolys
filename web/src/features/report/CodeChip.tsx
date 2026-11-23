import { CODE_META, GROUP_CLASS, SHORT } from "./codeMeta";

/** Short coloured chip for a code id (group colour from CODE_META). */
export function CodeChip({ id }: { id: string }) {
  const meta = CODE_META[id];
  return <span className={`code ${GROUP_CLASS[meta?.group ?? ""] ?? "c-info"}`}>{SHORT[id] ?? id}</span>;
}
