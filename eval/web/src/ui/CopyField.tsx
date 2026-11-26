import { CopyButton } from "./CopyButton";
import "./ui.css";

/** Labelled read-only value (e.g. an ID) with a copy action. Values live here, never in button labels. */
export function CopyField({ label, value }: { label: string; value: string }) {
  return <div className="ui-copyfield">
    <span className="ui-copyfield-label">{label}</span>
    <div className="ui-copyfield-row">
      <code className="ui-copyfield-value" title={value}>{value}</code>
      <CopyButton value={value} label={`Copy ${label.toLowerCase()}`} />
    </div>
  </div>;
}
