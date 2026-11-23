import { useEffect, useRef, useState } from 'react';
import type { CodedSpan, Dataset, DatasetMetadata, EvalApi, Mode, Options, RunInput, RunSummary, Upload } from './api';

export function plannedUnits(sessions: number, engines: string[], presets: string[], repeats: number): number {
  return sessions * ((engines.includes('human') ? 1 : 0) + engines.filter(e => e !== 'human').length * presets.length * repeats);
}
const message = (error: unknown) => error instanceof Error ? error.message : 'Something went wrong. Please try again.';
const toggle = (values: string[], value: string) => values.includes(value) ? values.filter(v => v !== value) : [...values, value];

export function NewRun({ api, onRunCreated, initialRun }: { api: EvalApi; onRunCreated: (id: string) => void; initialRun?: RunSummary }) {
  const rerunSourceID = initialRun?.run_id;
  const [mode, setMode] = useState<Mode>(initialRun && 'upload_id' in initialRun.input ? 'upload' : 'dataset');
  const [options, setOptions] = useState<Options>();
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [datasets, setDatasets] = useState<DatasetMetadata[]>([]);
  const [datasetId, setDatasetId] = useState('');
  const [dataset, setDataset] = useState<Dataset>();
  const [sessionIds, setSessionIds] = useState<string[]>([]);
  const [engines, setEngines] = useState<string[]>([]);
  const [presets, setPresets] = useState<string[]>([]);
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
  const [pollAttempt, setPollAttempt] = useState(0);
  const [pollFailed, setPollFailed] = useState(false);
  const uploadId = upload?.upload_id ?? (initialRun && 'upload_id' in initialRun.input ? initialRun.input.upload_id : undefined);
  const uploadStatus = upload?.status;

  useEffect(() => {
    let active = true;
    api.options(mode, mode === 'upload' ? uploadId : undefined).then(result => {
      if (!active) return;
      setOptions(result);
      setEngines((initialRun?.engines ?? result.defaults[mode].engines).filter(id => result.engines.some(e => e.id === id)));
      setPresets((initialRun?.presets ?? result.defaults[mode].presets).filter(name => result.presets.some(p => p.name === name)));
      setOptionsLoading(false);
    }).catch(e => { if (active) { setError(message(e)); setOptions(undefined); setEngines([]); setPresets([]); setOptionsLoading(false); } });
    return () => { active = false; };
  }, [api, mode, uploadId, loadAttempt, initialRun]);

  useEffect(() => {
    let active = true;
    if (rerunSourceID) return;
    api.datasets().then(result => {
      if (!active) return;
      setDatasets(result.datasets);
      setDatasetId(current => result.datasets.some(d => d.dataset_id === current) ? current : (result.datasets[0]?.dataset_id ?? ''));
    }).catch(e => { if (active) setError(message(e)); });
    return () => { active = false; };
  }, [api, loadAttempt, rerunSourceID]);

  useEffect(() => {
    if (rerunSourceID || !datasetId || mode !== 'dataset') return;
    let active = true;
    api.dataset(datasetId).then(result => {
      if (!active) return;
      setDataset(result); setSessionIds(result.sessions.map(s => s.session_id));
    }).catch(e => { if (active) setError(message(e)); });
    return () => { active = false; };
  }, [api, datasetId, mode, loadAttempt, rerunSourceID]);

  useEffect(() => {
    if (!uploadId || uploadStatus !== 'transcribing' || mode !== 'upload') return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await api.getUpload(uploadId, controller.signal);
        if (controller.signal.aborted) return;
        setUpload(result);
        if (result.status === 'transcribing') timer = setTimeout(() => void poll(), 3000);
      } catch (e) {
        if (!controller.signal.aborted) { setError(message(e)); setPollFailed(true); }
      }
    };
    timer = setTimeout(() => void poll(), 3000);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [api, uploadId, uploadStatus, mode, pollAttempt]);

  const invalidateUpload = () => {
    if (upload) setOptionsLoading(true);
    setUpload(undefined); setClinician(''); setPollFailed(false); setError('');
  };
  const changeMode = (next: Mode) => {
    if (mode === next) return;
    setMode(next); setOptions(undefined); setOptionsLoading(true); setEngines([]); setPresets([]); setError('');
    setDataset(undefined); setSessionIds([]);
  };
  const startNumber = Number(spanStart), endNumber = Number(spanEnd);
  const spanValid = !overrideSpan || (spanStart !== '' && spanEnd !== '' && Number.isInteger(startNumber) && Number.isInteger(endNumber) && startNumber >= 0 && endNumber > startNumber);
  const codedSpan: CodedSpan | undefined = !overrideSpan || !spanValid ? undefined : spanUnit === 'turns' ? { start_turn: startNumber, end_turn: endNumber } : { start_ms: startNumber, end_ms: endNumber };
  const visibleEngines = (options?.engines ?? []).filter(e => e.id !== 'human' || mode === 'dataset' || upload?.has_gold || !!rerunSourceID);
  const selectedEngines = engines.filter(id => visibleEngines.some(e => e.id === id));
  const sessionCount = initialRun ? ('session_ids' in initialRun.input ? initialRun.input.session_ids.length : 1) : mode === 'dataset' ? sessionIds.length : 1;
  const unitCount = plannedUnits(sessionCount, selectedEngines, presets, repeats);
  const canPrepare = !!file && !!goal.trim() && !!language.trim() && spanValid && !busy && !upload;
  const canStart = !busy && !optionsLoading && unitCount > 0 && selectedEngines.length > 0 && (selectedEngines.every(e => e === 'human') || presets.length > 0) && (!!rerunSourceID || (mode === 'dataset' ? !!dataset && dataset.dataset_id === datasetId && sessionIds.length > 0 : upload?.status === 'ready' && !!goal.trim() && !!language.trim() && spanValid));

  const mutate = async (operation: () => Promise<void>) => {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError('');
    try { await operation(); } catch (e) { setError(message(e)); }
    finally { inFlight.current = false; setBusy(false); }
  };
  const saveUpload = () => {
    if (!canPrepare || !file) return;
    void mutate(async () => {
      const saved = await api.upload({ file, ...(gold ? { gold } : {}), change_goal: goal.trim(), language: language.trim(), ...(codedSpan ? { coded_span: codedSpan } : {}) });
      setOptionsLoading(true); setUpload(saved); setClinician('');
    });
  };
  const startRun = () => {
    if (!canStart) return;
    if (rerunSourceID) {
      void mutate(async () => { const run = await api.rerun(rerunSourceID, { engines: selectedEngines, presets, repeats }); onRunCreated(run.run_id); });
      return;
    }
    const input: RunInput = {
      input: mode === 'dataset' ? { dataset_id: datasetId, session_ids: sessionIds } : { upload_id: upload!.upload_id },
      engines: selectedEngines, presets, repeats,
      ...(mode === 'upload' ? { change_goal: goal.trim(), language: language.trim(), ...(codedSpan ? { coded_span: codedSpan } : {}) } : {}),
    };
    void mutate(async () => { const run = await api.start(input); onRunCreated(run.run_id); });
  };

  return <section>
    <h1>New run</h1>
    <p>Compare MITI 4.2.1 coding across engines and human scores.</p>
    {error && <div role="alert"><p>{error}</p>{pollFailed ? <button type="button" onClick={() => { setError(''); setPollFailed(false); setPollAttempt(n => n + 1); }}>Retry transcription status</button> : <button type="button" disabled={busy} onClick={() => { setError(''); setOptionsLoading(true); setLoadAttempt(n => n + 1); }}>Reload choices</button>}</div>}
    <form aria-busy={busy} onSubmit={event => { event.preventDefault(); startRun(); }}>
      {busy && <p role="status">Working…</p>}
      {initialRun ? <fieldset><legend>Saved input</legend><p>Rerun of {rerunSourceID}. Original input and session configuration are preserved.</p><pre>{JSON.stringify({ input: initialRun.input, change_goal: initialRun.change_goal, language: initialRun.language, coded_span: initialRun.coded_span }, null, 2)}</pre></fieldset> : <fieldset disabled={busy}><legend>Input</legend>
        <div className="choice-row">{(['dataset', 'upload'] as const).map(value => <label key={value}><input type="radio" name="mode" checked={mode === value} onChange={() => changeMode(value)} />{value === 'dataset' ? 'Dataset' : 'Upload'}</label>)}</div>
        {mode === 'dataset' ? <>
          <label>Choose dataset<select value={datasetId} onChange={event => { setDatasetId(event.target.value); setDataset(undefined); setSessionIds([]); setError(''); }}><option value="" disabled>Select a dataset</option>{datasets.map(d => <option key={d.dataset_id} value={d.dataset_id}>{d.title}</option>)}</select></label>
          {dataset?.dataset_id === datasetId && <fieldset><legend>Sessions</legend>{dataset.sessions.map(s => <label key={s.session_id}><input type="checkbox" checked={sessionIds.includes(s.session_id)} onChange={() => setSessionIds(ids => toggle(ids, s.session_id))} />{s.title}</label>)}</fieldset>}
        </> : <>
          <label>Session file<input type="file" accept="audio/*,.json,.txt" onChange={event => { invalidateUpload(); setFile(event.target.files?.[0]); }} /></label>
          <label>Gold file (optional)<input type="file" accept=".json,application/json" onChange={event => { invalidateUpload(); setGold(event.target.files?.[0]); }} /></label>
          <label>Change goal<input value={goal} onChange={event => { invalidateUpload(); setGoal(event.target.value); }} /></label>
          <label>Language<input value={language} placeholder="e.g. en" onChange={event => { invalidateUpload(); setLanguage(event.target.value); }} /></label>
          <label><input type="checkbox" checked={overrideSpan} onChange={event => { invalidateUpload(); setOverrideSpan(event.target.checked); }} />Override coded portion</label>
          {overrideSpan && <fieldset><legend>Coded portion</legend><p>Start is included; end is excluded. Turn numbers start at zero.</p>
            <label>Measure in<select value={spanUnit} onChange={event => { invalidateUpload(); setSpanUnit(event.target.value); }}><option value="turns">Transcript turns</option><option value="ms">Milliseconds</option></select></label>
            <label>Start<input type="number" min="0" step="1" value={spanStart} onChange={event => { invalidateUpload(); setSpanStart(event.target.value); }} /></label>
            <label>End<input type="number" min="1" step="1" value={spanEnd} onChange={event => { invalidateUpload(); setSpanEnd(event.target.value); }} /></label>
            {!spanValid && <p>Enter whole numbers with end greater than start.</p>}
          </fieldset>}
          {gold && overrideSpan && <p>Human scores keep the coded portion in the gold file if it differs from your chosen portion.</p>}
          <button type="button" disabled={!canPrepare} onClick={saveUpload}>{busy && !upload ? 'Preparing…' : 'Prepare upload'}</button>
          {upload?.status === 'transcribing' && <p role="status">Transcribing recording…</p>}
          {upload?.status === 'ready' && <p role="status">Upload ready: {file?.name}</p>}
          {upload?.status === 'failed' && <div role="alert"><p>{upload.error?.message || 'Could not prepare this recording. Please try again.'}</p><button type="button" onClick={invalidateUpload}>Try upload again</button></div>}
          {upload?.status === 'awaiting_speakers' && <fieldset><legend>Pick the clinician</legend>
            <p>Choose the speaker who is the clinician in this session.</p>
            {upload.speakers.map(s => <div key={s.speaker}><label><input type="radio" name="clinician" checked={clinician === s.speaker} onChange={() => setClinician(s.speaker)} />{s.speaker}</label>{s.samples.map((sample, i) => <blockquote key={i}>{sample}</blockquote>)}</div>)}
            <button type="button" disabled={!clinician || busy} onClick={() => void mutate(async () => { setUpload(await api.speakers(upload.upload_id, clinician)); })}>Confirm clinician</button>
          </fieldset>}
        </>}
      </fieldset>}
      <fieldset disabled={busy || optionsLoading}><legend>Engines</legend>{optionsLoading && <p role="status">Loading choices…</p>}{visibleEngines.map(e => <label key={e.id}><input type="checkbox" checked={selectedEngines.includes(e.id)} onChange={() => setEngines(ids => toggle(ids, e.id))} />{e.label}{e.prod ? ' (prod)' : ''}</label>)}</fieldset>
      <fieldset disabled={busy || optionsLoading}><legend>Presets</legend>{options?.presets.map(p => <label key={p.name}><input type="checkbox" checked={presets.includes(p.name)} onChange={() => setPresets(names => toggle(names, p.name))} />{p.name}{p.prod ? ' (prod)' : ''}</label>)}</fieldset>
      <label>Runs per cell<select disabled={busy} value={repeats} onChange={event => setRepeats(Number(event.target.value) as 1 | 3)}><option value="1">1</option><option value="3">3</option></select></label>
      <p>Human scores use one unit per session.</p>
      <p className="planned" aria-live="polite">{unitCount} planned units</p>
      <button type="submit" disabled={!canStart}>{busy && upload?.status === 'ready' ? 'Working…' : 'Start run'}</button>
    </form>
  </section>;
}
