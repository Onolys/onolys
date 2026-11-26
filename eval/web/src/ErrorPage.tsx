import { Component, useEffect, useRef, type ReactNode } from 'react';
import { Button } from '@onolys/ui';

/** Same panel as prod's ErrorRecovery (web/src/components/ErrorRecovery.tsx): fixed copy, never the exception message. */
export function ErrorPage({ notFound = false, reload = () => window.location.reload() }: { notFound?: boolean; reload?: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  return <section role={notFound ? undefined : 'alert'} className="grid max-w-2xl gap-4 rounded-lg border border-border bg-card p-6 text-card-foreground">
    <h1 ref={heading} tabIndex={-1} className="text-2xl font-semibold">{notFound ? 'Page not found' : 'Something went wrong'}</h1>
    <p>{notFound ? "We couldn't find this page. Check the link or go back to New Run." : "We couldn't load this page. Reload to try again, or go back to New Run."}</p>
    {notFound && <p className="text-sm text-muted-foreground">Error 404</p>}
    <div className="flex flex-wrap items-center gap-4">
      {!notFound && <Button type="button" variant="outline" onClick={reload}>Reload page</Button>}
      <a href="/" className="text-primary underline underline-offset-4">Back to New Run</a>
    </div>
  </section>;
}

/** Catches render failures below it. `standalone` adds its own main landmark (used when the shell itself may be gone). */
export class ErrorBoundary extends Component<{ children: ReactNode; standalone?: boolean; resetKey?: string }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  /** A new `resetKey` (e.g. the location) gives the children another chance. */
  componentDidUpdate(prev: { resetKey?: string }) {
    if (this.state.failed && prev.resetKey !== this.props.resetKey) this.setState({ failed: false });
  }
  render() {
    if (!this.state.failed) return this.props.children;
    const page = <ErrorPage />;
    return this.props.standalone ? <main className="mx-auto max-w-2xl p-6">{page}</main> : page;
  }
}
