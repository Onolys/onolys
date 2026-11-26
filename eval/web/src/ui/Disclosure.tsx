import { ChevronRight } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import "./ui.css";

/** Collapsed-by-default section. `label` is a verb ("Show data"); content is not rendered while collapsed. Uses a native button so Enter/Space work. */
export function Disclosure({ label, defaultOpen = false, children }: { label: string; defaultOpen?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return <div className="ui-disclosure">
    <button type="button" className="ui-disclosure-toggle" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => setOpen((v) => !v)}>
      <ChevronRight aria-hidden="true" className={open ? "ui-disclosure-icon is-open" : "ui-disclosure-icon"} />
      {label}
    </button>
    {open ? <div id={id} className="ui-disclosure-body">{children}</div> : null}
  </div>;
}

export { Disclosure as ToggleSection };
