import { useRef, useState } from 'react';
import { Button } from '@onolys/common';
import type { RunDetail } from '../api';
import { PartialBadge, ProviderSkipNotices } from '../RunStatus';
import { RunConfigDialog } from '../RunConfigDialog';
import { Chip } from '../ui/Chip';
import { Disclosure } from '../ui/Disclosure';
import { SummaryCard } from '../ui/SummaryCard';
import type { CompareOverview } from './compareApi';
import { EvalLink, type CompareNavigate } from './CompareLink';
import { failedCombos } from './failedCombos';
import type { ComboLegendEntry } from './compareTypes';
import { sessionLabel } from './sessionLabel';
import './comparisonHeader.css';

const SHOWN_INCOMPLETE = 3;

function Labels({ data }: { data: CompareOverview }) {
 const labels = data.header.label_coverage;
 if (!labels) return <Chip tone="muted">No human labels</Chip>;
 return <>{labels.counts.length > 0 && <Chip tone="success">{labels.counts.length === 10 ? 'All 10 counts' : `${labels.counts.length} counts`}</Chip>}
  {labels.globals.length > 0 && <Chip tone="success">{labels.globals.length} globals</Chip>}</>;
}

function CoverageChips({ cohorts }: { cohorts: CompareOverview['cohorts'] }) {
 const rows = Object.entries(cohorts).map(([metric, cohort]) => ({ metric, ...cohort, ok: cohort.paired >= cohort.of }));
 const incomplete = rows.filter(row => !row.ok);
 const chip = (row: (typeof rows)[number]) => <Chip key={row.metric} tone={row.ok ? 'success' : 'warning'}>{row.metric}: paired {row.paired} of {row.of}</Chip>;
 const complete = rows.length - incomplete.length;
 return <>
  <div className="compare-chips"><Chip tone={incomplete.length ? 'warning' : 'success'}>{complete} of {rows.length} complete</Chip>{incomplete.slice(0, SHOWN_INCOMPLETE).map(chip)}</div>
  {incomplete.length > 0 && rows.length > Math.min(incomplete.length, SHOWN_INCOMPLETE) && <Disclosure label="Show all"><div className="compare-chips">{[...incomplete.slice(SHOWN_INCOMPLETE), ...rows.filter(row => row.ok)].map(chip)}</div></Disclosure>}
 </>;
}

/** Title, partial badge and four compact summary cards. Full coverage sits behind "Show all"; Config opens the saved-configuration popup. */
export function ComparisonHeader({ data, run, runId, navigate, legend, cohorts }: {
 data: CompareOverview; run?: RunDetail; runId: string; navigate: CompareNavigate; legend: ComboLegendEntry[];
 cohorts?: CompareOverview['cohorts'];
}) {
 const [config, setConfig] = useState<RunDetail | null>(null);
 const trigger = useRef<HTMLElement | null>(null);
 const cov = data.coverage;
 const failed = failedCombos(data);
 const letter = (key: string) => legend.find(item => item.combo.combo_key === key)?.letter ?? key;
 const otherExcluded = data.excluded.filter(item => !(item.combo_key && item.reason.startsWith('failed:')));
 const excludedItems = [...failed.map(item => ({ key: item.combo_key, text: `${letter(item.combo_key)}: ${item.code}`, tone: 'danger' as const })),
  ...[...new Map(otherExcluded.map(item => [`${item.session_id}|${item.combo_key}|${item.reason}`, item])).values()].map(item => ({ key: `${item.session_id}|${item.combo_key}|${item.reason}`, text: `${item.combo_key ? `${letter(item.combo_key)}: ` : `${sessionLabel(data.session_labels, item.session_id)}: `}${item.reason}`, tone: 'muted' as const }))];
 const total = failed.length + otherExcluded.length;
 const sub = failed.length ? (failed.every(item => item.all) ? 'all runs failed' : 'some runs failed') : excludedItems.length ? 'not compared' : 'Nothing excluded';
 return <header className="compare-header">
  <div className="compare-title">
   <div className="compare-title-row"><EvalLink state={{ view: 'run', run: runId }} navigate={navigate} className="compare-back"><span aria-hidden="true">←</span> Back to run</EvalLink>
    <h1>Compare - {data.header.name || runId}</h1>
    <PartialBadge run={{ status: cov.eval_status, cancelled_at: cov.cancelled_at, ...data.header.progress }}/>
    {run && <Button type="button" variant="outline" size="sm" onClick={event => { trigger.current = event.currentTarget; setConfig(run); }}>Config</Button>}</div>
   <ProviderSkipNotices skips={cov.skipped_providers}/>
  </div>
  <div className="compare-cards">
   <SummaryCard title="Sessions" value={data.header.sessions} sub={`${data.header.repeats} attempts each · ${data.combos.length} combos`}/>
   <SummaryCard title="Human labels" value={<span className="compare-chips"><Labels data={data}/></span>}/>
   <SummaryCard title="Coverage" value={<CoverageChips cohorts={cohorts ?? data.cohorts}/>} sub={`${cov.runs_done} of ${cov.runs_total} runs done, ${cov.runs_skipped} skipped`}/>
   <SummaryCard title="Excluded" value={total} sub={<>{excludedItems.length > 0 && <span className="compare-chips">{excludedItems.map(item => <Chip key={item.key} tone={item.tone}>{item.text}</Chip>)}</span>}<span>{sub}</span></>}/>
  </div>
  <RunConfigDialog run={config} returnFocus={trigger} onClose={() => setConfig(null)}/>
 </header>;
}
