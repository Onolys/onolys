import { useState, type ReactNode } from 'react';
import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@onolys/ui';

/** Pretty-printed text for any JSON value (JSON.stringify returns undefined for functions and undefined). */
export const prettyJson = (value: unknown) => JSON.stringify(value, null, 2) ?? '';

type JsonDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  /** Extra content between the header and the JSON (e.g. a copyable id). */
  extra?: ReactNode;
  /** The JSON value to show. Ignored while `loading` or `error` is set. */
  value?: unknown;
  loading?: boolean;
  error?: string;
  onRetry?: () => void;
  onCloseAutoFocus?: (event: Event) => void;
};

/** The one place JSON is shown: a modal with a scrollable monospace block (both axes), Copy, and the dialog's close button. Esc closes it. */
export function JsonDialog({ open, onOpenChange, title, description, extra, value, loading, error, onRetry, onCloseAutoFocus }: JsonDialogProps) {
  const [status, setStatus] = useState('');
  const json = loading || error ? '' : prettyJson(value);
  const change = (next: boolean) => { if (!next) setStatus(''); onOpenChange(next); };
  return <Dialog open={open} onOpenChange={change}>
    <DialogContent onCloseAutoFocus={onCloseAutoFocus} className="eval-config-dialog flex w-[90vw] max-w-[52rem] flex-col sm:max-w-[52rem]">
      <DialogHeader><DialogTitle>{title}</DialogTitle><DialogDescription>{description ?? 'Pretty-printed JSON. Scroll to read it, or copy it.'}</DialogDescription></DialogHeader>
      {extra}
      {error ? <div role="alert" className="grid gap-2"><p>{error}</p>{onRetry && <div><Button type="button" onClick={onRetry}>Retry JSON</Button></div>}</div>
        : loading ? <p role="status">Loading JSON…</p>
          : <div className="eval-config-json" data-testid="json-scroll" role="textbox" aria-readonly="true" aria-multiline="true" tabIndex={0} aria-label={`${title} (JSON)`}><pre>{json}</pre></div>}
      <DialogFooter>
        <span role="status">{status}</span>
        <Button type="button" variant="outline" disabled={!json} onClick={() => {
          void Promise.resolve().then(() => navigator.clipboard.writeText(json)).then(() => setStatus('Copied.')).catch(() => setStatus('Could not copy. Select the JSON to copy it manually.'));
        }}>Copy</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>;
}

/** A "View JSON" button that opens `value` in a JsonDialog. Never renders the JSON inline. */
export function JsonViewer({ value, title, label = 'View JSON' }: { value: unknown; title: string; label?: string }) {
  const [open, setOpen] = useState(false);
  return <>
    <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>{label}</Button>
    <JsonDialog open={open} onOpenChange={setOpen} title={title} value={value} />
  </>;
}
