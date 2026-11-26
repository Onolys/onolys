import type { MouseEvent, ReactNode } from 'react';
import type { RunSummary } from '../api';
import { buildCompareUrl, type CompareUrlState } from './compareUrl';
export type CompareNavigate = (state: CompareUrlState) => void;
export function EvalLink({ state, navigate, children, className }: { state: CompareUrlState; navigate: CompareNavigate; children: ReactNode; className?: string }) {
 const href = buildCompareUrl(state, window.location.search);
 const activate = (event: MouseEvent<HTMLAnchorElement>) => {
  if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) { event.preventDefault(); navigate(state); }
 };
 return <a href={href} onClick={activate} className={className}>{children}</a>;
}
export function CompareLink({ run, navigate }: { run: Pick<RunSummary,'run_id'|'status'>; navigate: CompareNavigate }) {
 return run.status === 'done' || run.status === 'partial' ? <EvalLink state={{run:run.run_id,view:'compare',tab:'overview'}} navigate={navigate}>Compare</EvalLink> : <span>Compare opens when the run has finished results</span>;
}
