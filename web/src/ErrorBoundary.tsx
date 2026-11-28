import { Component, type ReactNode } from "react";
import { ErrorRecovery } from "@onolys/common";
import { recoveryDetails } from "./api/errors";

/** Outside providers and router: their startup, effect and render failures need recovery too. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean; error?: unknown }> {
  state: { failed: boolean; error?: unknown } = { failed: false };
  static getDerivedStateFromError(error: unknown) { return { failed: true, error }; }
  render() {
    return this.state.failed
      ? <main className="mx-auto max-w-2xl p-6"><ErrorRecovery {...recoveryDetails(this.state.error)} /></main>
      : this.props.children;
  }
}
