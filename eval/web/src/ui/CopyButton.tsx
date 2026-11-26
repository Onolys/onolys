import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import "./ui.css";

/** Copies `value` to the clipboard. The label is a verb; the value itself is never shown on the button. */
export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      return;
    }
    setCopied(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1500);
  };
  return <button type="button" className="ui-copy" onClick={() => void copy()}>
    {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
    <span role="status">{copied ? "Copied" : label}</span>
  </button>;
}
