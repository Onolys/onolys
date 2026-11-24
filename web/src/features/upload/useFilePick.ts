/** Shared file pick with source-specific advisory pre-checks. */
import { useCallback, useEffect, useRef, useState } from "react";
import { useUploadLimits } from "./useUploadLimits";
import { checkFile, checkTranscript, readDuration, type PrecheckResult } from "./precheck";

export interface FilePick {
  file: File | null;
  check: PrecheckResult | null;
  /** The duration read is still running: the file cannot be submitted yet. */
  checking: boolean;
  /** Latest pick wins: a slower read of an earlier file never overwrites a newer check. */
  pick: (f: File | undefined) => Promise<void>;
  /** The file is usable: checked and not blocked. */
  ready: boolean;
}

export function useFilePick(kind: "audio" | "transcript" = "audio"): FilePick {
  const [file, setFile] = useState<File | null>(null);
  const [check, setCheck] = useState<PrecheckResult | null>(null);
  const [checking, setChecking] = useState(false);
  const latest = useRef<File | undefined>(undefined);
  // Served limits (R10). Read at pick time through a ref; unloaded = the checks skip (server decides).
  const limits = useUploadLimits();
  const limitsRef = useRef(limits);
  useEffect(() => {
    limitsRef.current = limits;
  }, [limits]);

  const pick = useCallback(async (f: File | undefined) => {
    latest.current = f;
    setFile(f ?? null);
    setCheck(null);
    setChecking(false);
    if (!f) return;
    if (kind === "transcript") return setCheck(checkTranscript(f));
    const quick = checkFile(f, null, limitsRef.current);
    if (quick.blocked) return setCheck(quick);
    setChecking(true);
    const duration = await readDuration(f);
    if (latest.current !== f) return; // a newer pick owns the state now
    setCheck(checkFile(f, duration, limitsRef.current));
    setChecking(false);
  }, [kind]);

  return { file, check, checking, pick, ready: file !== null && check !== null && check.blocked === null };
}
