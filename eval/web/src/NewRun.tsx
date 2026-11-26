import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Button, Input, Textarea } from '@onolys/ui';
import { ColdStartNotice } from './ColdStart';
import { sourceLine, originalMedia } from './sourceMedia';
import type { CodedSpan, Dataset, DatasetMetadata, EvalApi, Mode, Options, RunInput, RunSummary, Selection, Upload, UploadInput } from './api';
import { MAX_UNITS, countText, effortsFor, modelMap, planCount, skippedText, tiersFor, tooLargeMessage, validateSelection, comboKey } from './matrix';

const emptySelection: Selection = { models: [], tiers: [], efforts: [] };
const message = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Please try again.';
const POLL_MS = 3000, MAX_POLL_MS = 30000;
/** Explicit Human comparison requires gold. Unknown (older server) counts as available. */
const hasGold = (session: { has_gold?: boolean }) => session.has_gold !== false;
const MAX_GOAL = 4000; // RunRequest.change_goal limit
const toggle = (values: string[], value: string) => values.includes(value) ? values.filter(v => v !== value) : [...values, value];

const DEFAULT_SESSIONS = 50;

export function NewRun({ api, onRunCreated, initialRun }: { api: EvalApi; onRunCreated: (id: string) => void; initialRun?: RunSummary }) {
  const rerunSourceID = initialRun?.run_id;
  const [name, setName] = useState(initialRun?.name ?? '');
  const [description, setDescription] = useState(initialRun?.description ?? '');
  const [mode, setMode] = useState<Mode>(initialRun && 'upload_id' in initialRun.input ? 'upload' : 'dataset');
  const [options, setOptions] = useState<Options>();
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [datasets, setDatasets] = useState<DatasetMetadata[]>([]);
  const [datasetId, setDatasetId] = useState('');
  const [dataset, setDataset] = useState<Dataset>();
  const [sessionLimit, setSessionLimit] = useState(0);
  const [engines, setEngines] = useState<string[]>([]);
  const [selection, setSelection] = useState<Selection>(emptySelection);
  const [repeats, setRepeats] = useState<1 | 3>(initialRun?.repeats ?? 1);
  const [file, setFile] = useState<File>();
  const [gold, setGold] = useState<File>();
  const [goal, setGoal] = useState('');
  const [language, setLanguage] = useState('');
  const [overrideSpan, setOverrideSpan] = useState(false);
  const [spanUnit, setSpanUnit] = useState('turns');
  const [spanStart, setSpanStart] = useState('0');
  const [spanEnd, setSpanEnd] = useState('');
  const [upload, setUpload] = useState<Upload>();
  const [clinician, setClinician] = useState('');
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState('');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [errorKind, setErrorKind] = useState<'load' | 'action'>('load');
  const [pollError, setPollError] = useState('');
  const lastAction = useRef<(() => Promise<void>) | undefined>(undefined);
  const uploadId = upload?.upload_id ?? (initialRun && 'upload_id' in initialRun.input ? initialRun.input.upload_id : undefined);
  const uploadStatus = upload?.status;

  useEffect(() => {
    let active = true;
    api.options(mode, mode === 'upload' ? uploadId : undefined).then(result => {
      if (!active) return;
      setOptions(result);
      setEngines(initialRun?.engines ?? result.defaults[mode].engines);
      setSelection(initialRun ? (initialRun.legacy_selection || !initialRun.selection ? emptySelection : initialRun.selection) : result.defaults[mode].selection);
      setOptionsLoading(false);
    }).catch(e => { if (active) { setErrorKind('load'); setError(message(e)); setOptions(undefined); setEngines([]); setSelection(emptySelection); setOptionsLoading(false); } });
    return () => { active = false; };
  }, [api, mode, uploadId, loadAttempt, initialRun]);

  useEffect(() => {
    let active = true;
    if (rerunSourceID) return;
    api.datasets().then(result => {
      if (!active) return;
      setDatasets(result.datasets);
      setDatasetId(current => result.datasets.some(d => d.dataset_id === current) ? current : (result.datasets[0]?.dataset_id ?? ''));
    }).catch(e => { if (active) { setErrorKind('load'); setError(message(e)); } });
    return () => { active = false; };
  }, [api, loadAttempt, rerunSourceID]);

  useEffect(() => {
    if (rerunSourceID || !datasetId || mode !== 'dataset') return;
    let active = true;
    api.dataset(datasetId).then(result => {
      if (!active) return;
      setDataset(result); setSessionLimit(Math.min(DEFAULT_SESSIONS, result.sessions.length));
    }).catch(e => { if (active) { setErrorKind('load'); setError(message(e)); } });
    return () => { active = false; };
  }, [api, datasetId, mode, loadAttempt, rerunSourceID]);

  useEffect(() => {
    if (!uploadId || uploadStatus !== 'transcribing' || mode !== 'upload') return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    const poll = async () => {
      try {
        const result = await api.getUpload(uploadId, controller.signal);
        if (controller.signal.aborted) return;
        failures = 0; setPollError('');
        setUpload(result);
        if (result.status === 'transcribing') timer = setTimeout(() => void poll(), POLL_MS);
      } catch (e) {
        if (controller.signal.aborted) return;
        failures += 1; setPollError(message(e));
        timer = setTimeout(() => void poll(), Math.min(POLL_MS * 2 ** failures, MAX_POLL_MS));
      }
    };
    timer = setTimeout(() => void poll(), POLL_MS);
    return () => { clearTimeout(timer); controller.abort(); setPollError(''); };
  }, [api, uploadId, uploadStatus, mode]);

  const invalidateUpload = () => {
    if (upload) setOptionsLoading(true);
    setUpload(undefined); setClinician(''); setPollError(''); setError('');
  };
  const changeMode = (next: Mode) => {
    if (mode === next) return;
    setMode(next); setOptions(undefined); setOptionsLoading(true); setEngines([]); setSelection(emptySelection); setError('');
    setDataset(undefined); setSessionLimit(0);
  };
  const datasetReady = !!dataset && dataset.dataset_id === datasetId;
  const visibleEngines = (options?.engines ?? []).filter(e => e.id !== 'human' || mode === 'dataset' || upload?.has_gold || !!rerunSourceID);
  const humanAvailable = !!initialRun || mode !== 'dataset' || !datasetReady || dataset.sessions.some(hasGold);
  const unavailableEngines = engines.filter(id => !visibleEngines.some(e => e.id === id));
  const unavailableModels = selection.models.filter(id => !options?.models.some(m => m.id === id));
  const availableTiers = (options?.models ?? []).filter(m => selection.models.includes(m.id)).flatMap(m => m.tiers);
  const unavailableTiers = selection.tiers.filter(id => !availableTiers.some(t => t.id === id));
  const unavailableEfforts = selection.efforts.filter(id => !effortsFor(options?.models ?? [], selection.tiers).includes(id));
  const unavailable = [...unavailableEngines, ...unavailableModels, ...unavailableTiers, ...unavailableEfforts];
  const finalEngines = engines.filter(id => visibleEngines.some(e => e.id === id) && (id !== 'human' || humanAvailable));
  const needsGold = finalEngines.includes('human');
  const eligibleSessions = datasetReady ? dataset.sessions.filter(s => !needsGold || hasGold(s)) : [];
  const totalSessions = eligibleSessions.length;
  const shownLimit = Math.min(sessionLimit, totalSessions);
  const sessionIds = eligibleSessions.slice(0, shownLimit).map(s => s.session_id);
  const startNumber = Number(spanStart), endNumber = Number(spanEnd);
  const spanValid = !overrideSpan || (spanStart !== '' && spanEnd !== '' && Number.isInteger(startNumber) && Number.isInteger(endNumber) && startNumber >= 0 && endNumber > startNumber);
  const codedSpan: CodedSpan | undefined = !overrideSpan || !spanValid ? undefined : spanUnit === 'turns' ? { start_turn: startNumber, end_turn: endNumber } : { start_ms: startNumber, end_ms: endNumber };
  const sessionCount = initialRun ? ('session_ids' in initialRun.input ? initialRun.input.session_ids.length : 1) : mode === 'dataset' ? sessionIds.length : 1;
  const needsCombos = finalEngines.some(e => e !== 'human');
  const validation = validateSelection(modelMap(options?.models ?? []), selection, needsCombos);
  const combos = validation.error === undefined ? validation.combos : [];
  const dropped = validation.error === undefined ? validation.dropped : [];
  const plan = planCount(sessionCount, finalEngines, combos.length, repeats);
  const unitCount = plan.units;
  const tooLarge = unitCount > MAX_UNITS;
  const tiers = tiersFor(options?.models ?? [], selection.models);
  const efforts = effortsFor(options?.models ?? [], selection.tiers);
  const pruneEfforts = (next: Selection): Selection => ({ ...next, efforts: next.efforts.filter(e => effortsFor(options?.models ?? [], next.tiers).includes(e)) });
  const toggleModel = (id: string) => setSelection(cur => {
    if (!cur.models.includes(id)) return { ...cur, models: [...cur.models, id] };
    const own = new Set((options?.models ?? []).find(m => m.id === id)?.tiers.map(t => t.id));
    return pruneEfforts({ ...cur, models: cur.models.filter(m => m !== id), tiers: cur.tiers.filter(t => !own.has(t)) });
  });
  const toggleTier = (id: string) => setSelection(cur => cur.tiers.includes(id) ? pruneEfforts({ ...cur, tiers: cur.tiers.filter(t => t !== id) }) : { ...cur, tiers: [...cur.tiers, id] });
  const toggleEffort = (id: string) => setSelection(cur => ({ ...cur, efforts: toggle(cur.efforts, id) }));
  const canPrepare = !!file && !!goal.trim() && !!language.trim() && spanValid && !busy && !upload;
  const canStart = unavailable.length === 0 && !busy && !optionsLoading && unitCount > 0 && !tooLarge && finalEngines.length > 0 && validation.error === undefined && (!!rerunSourceID || (mode === 'dataset' ? datasetReady && sessionIds.length > 0 : upload?.status === 'ready' && !!goal.trim() && !!language.trim() && spanValid));

  const mutate = async (operation: () => Promise<void>) => {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(''); lastAction.current = operation;
    try { await operation(); } catch (e) { setErrorKind('action'); setError(message(e)); }
    finally { inFlight.current = false; setBusy(false); }
  };
  const saveUpload = () => {
    if (!canPrepare || !file) return;
    const input: UploadInput = { file, ...(gold ? { gold } : {}), change_goal: goal.trim(), language: language.trim(), ...(codedSpan ? { coded_span: codedSpan } : {}) };
    void mutate(async () => {
      const saved = await api.upload(input);
      setOptionsLoading(true); setUpload(saved); setClinician('');
    });
  };
  const runDetails = { ...(name || initialRun?.name !== undefined ? { name: name || null } : {}), ...(description || initialRun?.description !== undefined ? { description: description || null } : {}) };
  const startRun = () => {
    if (!canStart) return;
    if (rerunSourceID) {
      void mutate(async () => { const run = await api.rerun(rerunSourceID, { engines: finalEngines, selection, repeats, ...runDetails }); onRunCreated(run.run_id); });
      return;
    }
    const input: RunInput = {
      input: mode === 'dataset' ? { dataset_id: datasetId, session_ids: sessionIds } : { upload_id: upload!.upload_id },
      engines: finalEngines, selection, repeats, ...runDetails,
      ...(mode === 'upload' ? { change_goal: goal.trim(), language: language.trim(), ...(codedSpan ? { coded_span: codedSpan } : {}) } : {}),
    };
    void mutate(async () => { const run = await api.start(input); onRunCreated(run.run_id); });
  };

  const selectedDataset = datasets.find(d => d.dataset_id === datasetId);
  return <section className="new-run">
    <h1>New run</h1>
    <p>Compare MITI 4.2.1 coding across engines and human scores.</p>
    {error && <div role="alert"><p>{error}</p>{errorKind === 'action' ? <Button type="button" disabled={busy} onClick={() => { const action = lastAction.current; if (action) void mutate(action); else setError(''); }}>Retry</Button> : <Button type="button" disabled={busy} onClick={() => { setError(''); setOptionsLoading(true); setLoadAttempt(n => n + 1); }}>Reload choices</Button>}</div>}
    <form aria-busy={busy} onSubmit={event => { event.preventDefault(); startRun(); }}>
      {busy && <p role="status">Working…</p>}
      <fieldset disabled={busy}><legend>Run details</legend>
        <label>Name (optional)<Input value={name} maxLength={200} onChange={event => setName(event.target.value)} /></label>
        <label>Description (optional)<Textarea value={description} maxLength={4000} rows={3} onChange={event => setDescription(event.target.value)} /></label>
      </fieldset>
      {initialRun ? <fieldset><legend>Saved input</legend><p>Rerun of {rerunSourceID}. Original input and session configuration are preserved.</p><p>{'dataset_id' in initialRun.input ? `Dataset: ${initialRun.input.dataset_id} · ${initialRun.input.session_ids.length} saved sessions` : `Upload: ${initialRun.input.upload_id}`}</p></fieldset> : <fieldset disabled={busy}><legend>Input</legend>
        <div className="choice-row">{(['dataset', 'upload'] as const).map(value => <label key={value}><input type="radio" name="mode" checked={mode === value} onChange={() => changeMode(value)} />{value === 'dataset' ? 'Dataset' : 'Upload'}</label>)}</div>
        {mode === 'dataset' ? <>
          <label>Choose dataset<select value={datasetId} onChange={event => { setDatasetId(event.target.value); setDataset(undefined); setSessionLimit(0); setError(''); }}><option value="" disabled>Select a dataset</option>{datasets.map(d => <option key={d.dataset_id} value={d.dataset_id}>{d.title} ({originalMedia(d.source_media)})</option>)}</select></label>
          {selectedDataset && <dl className="dataset-source" data-testid="dataset-source">{sourceLine(selectedDataset).split(' · ').map(line => { const separator = line.indexOf(':'); return <div key={line}><dt>{separator >= 0 ? line.slice(0, separator) : 'MITI version'}</dt><dd>{separator >= 0 ? line.slice(separator + 2) : line}</dd></div>; })}</dl>}
          {datasetReady && totalSessions > 0 && <label className="session-limit">Sessions to run: {shownLimit} of {totalSessions}<input type="range" style={{ '--range-fill': `${totalSessions <= 1 ? 100 : (shownLimit - 1) / (totalSessions - 1) * 100}%` } as CSSProperties} min={1} max={totalSessions} step={1} value={shownLimit} aria-valuetext={`${shownLimit} of ${totalSessions} sessions`} onChange={event => setSessionLimit(Number(event.target.value))} /></label>}
          {datasetReady && !humanAvailable && <p>Human comparison is unavailable because these sessions have no gold files. AI engines can run all sessions.</p>}
          {datasetReady && dataset!.sessions.length > totalSessions && <p role="status">{totalSessions === 0 ? "None of this dataset's sessions has a gold file, so none can be run." : `${dataset!.sessions.length - totalSessions} session(s) without a gold file are excluded, while Human is selected. Deselect Human to run those sessions with AI engines.`}</p>}
        </> : <>
          <label>Session file<Input type="file" accept=".mp3,.wav,.m4a,.webm,.ogg,.json,.txt" onChange={event => { invalidateUpload(); setFile(event.target.files?.[0]); }} /></label>
          <p>Recordings up to 300 MiB. Files over 25 MiB upload directly to storage. Keep this page open; refreshing starts a new upload.</p>
          <label>Gold file (optional)<Input type="file" accept=".json,application/json" onChange={event => { invalidateUpload(); setGold(event.target.files?.[0]); }} /></label>
          <label>Change goal<Input value={goal} maxLength={MAX_GOAL} onChange={event => { invalidateUpload(); setGoal(event.target.value); }} /></label><small>{goal.length} / {MAX_GOAL}</small>
          <label>Language<Input value={language} placeholder="e.g. en" onChange={event => { invalidateUpload(); setLanguage(event.target.value); }} /></label>
          <label><input type="checkbox" checked={overrideSpan} onChange={event => { invalidateUpload(); setOverrideSpan(event.target.checked); }} />Override coded portion</label>
          {overrideSpan && <fieldset><legend>Coded portion</legend><p>Start is included; end is excluded. Turn numbers start at zero.</p>
            <label>Measure in<select value={spanUnit} onChange={event => { invalidateUpload(); setSpanUnit(event.target.value); }}><option value="turns">Transcript turns</option><option value="ms">Milliseconds</option></select></label>
            <label>Start<Input type="number" min="0" step="1" value={spanStart} onChange={event => { invalidateUpload(); setSpanStart(event.target.value); }} /></label>
            <label>End<Input type="number" min="1" step="1" value={spanEnd} onChange={event => { invalidateUpload(); setSpanEnd(event.target.value); }} /></label>
            {!spanValid && <p>Enter whole numbers with end greater than start.</p>}
          </fieldset>}
          {gold && overrideSpan && <p>Human scores keep the coded portion in the gold file if it differs from your chosen portion.</p>}
          <Button type="button" disabled={!canPrepare} onClick={saveUpload}>{busy && !upload ? 'Preparing…' : 'Prepare upload'}</Button>
          {upload?.status === 'transcribing' && <p role="status">Transcribing recording…</p>}{pollError && <p role="status">Could not check transcription status ({pollError}). Still trying…</p>}
          {upload?.status === 'ready' && <p role="status">Upload ready: {file?.name}</p>}
          {upload?.status === 'failed' && <div role="alert"><p>{upload.error?.message || 'Could not prepare this recording. Please try again.'}</p><Button type="button" onClick={invalidateUpload}>Try upload again</Button></div>}
          {upload?.status === 'awaiting_speakers' && <fieldset><legend>Pick the clinician</legend>
            <p>Choose the speaker who is the clinician in this session.</p>
            {upload.speakers.map(s => <div key={s.speaker}><label><input type="radio" name="clinician" checked={clinician === s.speaker} onChange={() => setClinician(s.speaker)} />{s.speaker}</label>{s.samples.map((sample, i) => <blockquote key={i}>{sample}</blockquote>)}</div>)}
            <Button type="button" disabled={!clinician || busy} onClick={() => void mutate(async () => { setUpload(await api.speakers(upload.upload_id, clinician)); })}>Confirm clinician</Button>
          </fieldset>}
        </>}
      </fieldset>}
      {initialRun?.legacy_selection && <p role="status">This older run chose models by preset, which can no longer be recreated. Pick a model, tier and effort below; saved input and engines are kept.</p>}
      <div className="configuration-row">
      <fieldset disabled={busy || optionsLoading}><legend>Engines</legend>{optionsLoading && <p role="status">Loading choices…</p>}<ColdStartNotice pending={optionsLoading && !error} />{unavailableEngines.map(id => <label key={id}><input type="checkbox" checked onChange={() => setEngines(ids => ids.filter(e => e !== id))} />{id} (unavailable)</label>)}{visibleEngines.map(e => <label key={e.id}><input type="checkbox" checked={finalEngines.includes(e.id)} disabled={e.id === 'human' && !humanAvailable} onChange={() => setEngines(ids => toggle(ids, e.id))} />{e.label}</label>)}</fieldset>
      <fieldset disabled={busy || optionsLoading}><legend>Models</legend>{unavailableModels.map(id => <label key={id}><input type="checkbox" checked onChange={() => toggleModel(id)} />{id} (unavailable)</label>)}{options?.models.map(m => <label key={m.id}><input type="checkbox" checked={selection.models.includes(m.id)} onChange={() => toggleModel(m.id)} />{m.label}</label>)}</fieldset>
      <fieldset disabled={busy || optionsLoading}><legend>Tiers</legend>{unavailableTiers.map(id => <label key={id}><input type="checkbox" checked onChange={() => toggleTier(id)} />{id} (unavailable)</label>)}{tiers.map(t => <label key={t.id}><input type="checkbox" checked={selection.tiers.includes(t.id)} onChange={() => toggleTier(t.id)} />{t.id}</label>)}</fieldset>
      <fieldset disabled={busy || optionsLoading}><legend>Efforts</legend>{unavailableEfforts.map(id => <label key={id}><input type="checkbox" checked onChange={() => toggleEffort(id)} />{id} (unavailable)</label>)}{efforts.map(e => <label key={e}><input type="checkbox" checked={selection.efforts.includes(e)} onChange={() => toggleEffort(e)} />{e}</label>)}</fieldset>
      </div>
      {unavailable.length > 0 && <p role="status">Saved choices are unavailable: {unavailable.join(', ')}. Remove them or choose available replacements before starting.</p>}
      <label>Runs per cell<select disabled={busy} value={repeats} onChange={event => setRepeats(Number(event.target.value) as 1 | 3)}><option value="1">1</option><option value="3">3</option></select></label>
      <p>Each repeat codes the same session again with each selected engine and model configuration. Choose 3 to compare variation between attempts. Human scores are included once per session.</p>
      <p className="planned" aria-live="polite">{countText(plan)}</p>
      {combos.length > 0 && <details><summary>Combos ({combos.length})</summary><ul>{combos.map(c => <li key={comboKey(c)}>{comboKey(c)}</li>)}</ul></details>}
      {dropped.length > 0 && <ul aria-label="Skipped combos">{skippedText(dropped).map(t => <li key={t}>{t}</li>)}</ul>}
      {tooLarge ? <p role="status">{tooLargeMessage(unitCount)}</p> : validation.error !== undefined && !(selection.models.length === 0 && selection.tiers.length === 0 && selection.efforts.length === 0 && !needsCombos) && <p role="status">{validation.error}</p>}
      <Button type="submit" disabled={!canStart}>{busy && upload?.status === 'ready' ? 'Working…' : 'Start run'}</Button>
    </form>
  </section>;
}
