// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import fixture from '../../fixtures/selection_cases.json';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NewRun } from './NewRun';
import { createEvalApi, type EvalApi, type Options, type RunSummary, type Upload } from './api';

afterEach(() => { cleanup(); vi.useRealTimers(); });
const sonnetLow = { models: ['claude'], tiers: ['claude-sonnet-5-5'], efforts: ['low'] };
const options: Options = {
  engines: [{ id: 'human', engine: 'human', label: 'Human score', prod: false }, { id: 'miti', engine: 'miti', label: 'MITI lean (prod)', prod: true }, { id: 'oneshot:miti', engine: 'oneshot', config: 'miti', label: 'One-shot · MITI', prod: false }],
  models: Object.entries(fixture.models).map(([id, tiers]) => ({ id, label: id === 'claude' ? 'Claude' : 'Gemini', context_tokens: 1000, max_output_tokens: 100, tiers: Object.entries(tiers).map(([tier, efforts]) => ({ id: tier, efforts, default_effort: 'low' })) })),
  defaults: { dataset: { engines: ['human', 'miti'], selection: sonnetLow, label: 'Claude / claude-sonnet-5-5 / low (prod)' }, upload: { engines: ['miti'], selection: sonnetLow, label: 'Claude / claude-sonnet-5-5 / low (prod)' } },
};
function makeApi(sessionCount = 2) {
  return {
    ...createEvalApi('', vi.fn()),
    me: vi.fn().mockResolvedValue({}),
    options: vi.fn(async (_mode: string, uploadId?: string) => ({ ...options, engines: uploadId === 'gold' || _mode === 'dataset' ? options.engines : options.engines.filter(e => e.id !== 'human') })),
    datasets: vi.fn().mockResolvedValue({ datasets: [{ dataset_id: 'sample', title: 'Sample dataset' }] }),
    dataset: vi.fn().mockResolvedValue({ dataset_id: 'sample', title: 'Sample dataset', sessions: sessionCount === 2 ? [{ session_id: 's1', title: 'First session' }, { session_id: 's2', title: 'Second session' }] : Array.from({ length: sessionCount }, (_, i) => ({ session_id: i === 0 ? 's1' : `x${i}`, title: i === 0 ? 'First session' : `Session ${i}` })) }),
    upload: vi.fn().mockResolvedValue({ upload_id: 'plain', status: 'ready', has_gold: false, speakers: [] }),
    getUpload: vi.fn().mockResolvedValue({ upload_id: 'plain', status: 'ready', has_gold: false, speakers: [] }),
    speakers: vi.fn().mockResolvedValue({ upload_id: 'plain', status: 'ready', has_gold: false, speakers: [] }),
    start: vi.fn().mockResolvedValue({ run_id: 'run-1', status: 'queued' }),
    rerun: vi.fn().mockResolvedValue({ run_id: 'run-2', status: 'queued' }),
  } satisfies EvalApi;
}
async function mount(sessionCount = 2) {
  const api = makeApi(sessionCount); const onRunCreated = vi.fn();
  render(<NewRun api={api} onRunCreated={onRunCreated} />);
  await screen.findByLabelText('First session');
  return { api, onRunCreated };
}
async function uploadMode() {
  const ctx = await mount();
  fireEvent.click(screen.getByLabelText('Upload'));
  await waitFor(() => expect(screen.queryByLabelText('Human score')).toBeNull());
  fireEvent.change(screen.getByLabelText('Change goal'), { target: { value: 'Reduce smoking' } });
  fireEvent.change(screen.getByLabelText('Language'), { target: { value: 'en' } });
  return ctx;
}
function chooseFile(label = 'Session file', name = 'session.txt') {
  fireEvent.change(screen.getByLabelText(label), { target: { files: [new File(['example'], name)] } });
}
const checked = (name: string) => (screen.getByLabelText(name) as HTMLInputElement).checked;
const start = () => screen.getByRole('button', { name: 'Start run' }) as HTMLButtonElement;

describe('new run', () => {
  it('loads configured dataset defaults, all sessions, prod labels and starts with a selection', async () => {
    const { api, onRunCreated } = await mount();
    expect(checked('First session')).toBe(true); expect(checked('Second session')).toBe(true);
    expect(checked('Human score')).toBe(true); expect((screen.getByLabelText('Human score') as HTMLInputElement).disabled).toBe(true);
    expect(checked('MITI lean (prod)')).toBe(true);
    expect(checked('Claude')).toBe(true); expect(checked('claude-sonnet-5-5')).toBe(true); expect(checked('low')).toBe(true);
    expect(screen.getByText('4 units = 2 sessions x (1 human + 1 engines x 1 combos x 1 repeats)')).toBeTruthy();
    fireEvent.click(start());
    await waitFor(() => expect(api.start).toHaveBeenCalledWith({ input: { dataset_id: 'sample', session_ids: ['s1', 's2'] }, engines: ['human', 'miti'], selection: sonnetLow, repeats: 1 }));
    expect(onRunCreated).toHaveBeenCalledWith('run-1');
  });
  it('deselecting a model drops its tiers and the efforts only they offered', async () => {
    await mount();
    expect(screen.queryByLabelText('gemini-4-neon')).toBeNull();
    fireEvent.click(screen.getByLabelText('Gemini')); fireEvent.click(screen.getByLabelText('gemini-4-neon'));
    expect(checked('gemini-4-neon')).toBe(true);
    fireEvent.click(screen.getByLabelText('Gemini'));
    expect(screen.queryByLabelText('gemini-4-neon')).toBeNull();
    fireEvent.click(screen.getByLabelText('Gemini'));
    expect(checked('gemini-4-neon')).toBe(false);
  });
  it('effort list is the union of the selected tiers efforts', async () => {
    await mount();
    expect(screen.getAllByRole('checkbox').map(c => c.parentElement?.textContent)).toContain('max');
    fireEvent.click(screen.getByLabelText('Claude')); // no tiers left
    expect(screen.queryByLabelText('max')).toBeNull();
    fireEvent.click(screen.getByLabelText('Gemini')); fireEvent.click(screen.getByLabelText('gemini-4-neon'));
    expect(screen.queryByLabelText('max')).toBeNull(); expect(screen.getByLabelText('high')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Claude')); fireEvent.click(screen.getByLabelText('claude-haiku-5-5'));
    expect(screen.getByLabelText('max')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('max'));
    fireEvent.click(screen.getByLabelText('claude-haiku-5-5')); // drops max again, effort pruned
    expect(screen.queryByLabelText('max')).toBeNull();
  });
  it('shows the shared-fixture count, combo list and skipped combos', async () => {
    await mount();
    fireEvent.click(screen.getByLabelText('Gemini')); fireEvent.click(screen.getByLabelText('gemini-4-neon'));
    fireEvent.click(screen.getByLabelText('low')); fireEvent.click(screen.getByLabelText('max'));
    expect(screen.getByText('4 units = 2 sessions x (1 human + 1 engines x 1 combos x 1 repeats)')).toBeTruthy();
    expect(screen.getByText('claude/claude-sonnet-5-5/max')).toBeTruthy();
    expect(screen.getByText('skipped: gemini-4-neon has no max')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('One-shot · MITI'));
    fireEvent.change(screen.getByLabelText('Runs per cell'), { target: { value: '3' } });
    expect(screen.getByText('14 units = 2 sessions x (1 human + 2 engines x 1 combos x 3 repeats)')).toBeTruthy();
  });
  it('disables Start with the server message above 499 units', async () => {
    await mount(250);
    expect(screen.getByText('Run has 500 units; the maximum is 499. Remove sessions, combos or repeats.')).toBeTruthy();
    expect(start().disabled).toBe(true);
    fireEvent.click(screen.getByLabelText('First session'));
    expect(screen.queryByText(/the maximum is 499/)).toBeNull();
    expect(start().disabled).toBe(false);
  });
  it('legacy rerun opens the picker empty with a notice and keeps the saved engines', async () => {
    const api = makeApi(); const onRunCreated = vi.fn();
    const legacy = { run_id: 'old', status: 'done', created_at: '', input: { dataset_id: 'sample', session_ids: ['s1'] }, engines: ['miti'], repeats: 1, selection: null, combos: null, presets: ['default'], legacy_selection: true, combo_keys: ['preset:default'], combo_labels: { 'preset:default': 'preset: default (legacy)' } } as unknown as RunSummary;
    render(<NewRun api={api} initialRun={legacy} onRunCreated={onRunCreated} />);
    expect(await screen.findByText(/older run chose models by preset/)).toBeTruthy();
    expect(checked('MITI lean (prod)')).toBe(true); expect(checked('Human score')).toBe(true);
    expect(checked('Claude')).toBe(false); expect(checked('Gemini')).toBe(false);
    expect(start().disabled).toBe(true);
    fireEvent.click(screen.getByLabelText('Claude')); fireEvent.click(screen.getByLabelText('claude-haiku-5-5')); fireEvent.click(screen.getByLabelText('high'));
    expect(start().disabled).toBe(false);
    fireEvent.click(start());
    await waitFor(() => expect(api.rerun).toHaveBeenCalledWith('old', { engines: ['human', 'miti'], selection: { models: ['claude'], tiers: ['claude-haiku-5-5'], efforts: ['high'] }, repeats: 1 }));
  });
  it('requires a combo when an AI engine is selected and allows Human only', async () => {
    await mount();
    fireEvent.click(screen.getByLabelText('low'));
    expect(start().disabled).toBe(true);
    fireEvent.click(screen.getByLabelText('MITI lean (prod)'));
    expect(start().disabled).toBe(false);
  });
  it('upload defaults omit Human and require a saved ready upload; changing input invalidates it', async () => {
    const { api } = await uploadMode();
    expect(checked('MITI lean (prod)')).toBe(true); expect(start().disabled).toBe(true);
    chooseFile();
    fireEvent.change(screen.getByLabelText('Change goal'), { target: { value: 'Reduce smoking' } });
    fireEvent.change(screen.getByLabelText('Language'), { target: { value: 'en' } });
    fireEvent.click(screen.getByRole('button', { name: 'Prepare upload' }));
    await waitFor(() => expect(start().disabled).toBe(false));
    expect(api.upload).toHaveBeenCalledOnce();
    fireEvent.change(screen.getByLabelText('Change goal'), { target: { value: 'A different goal' } });
    expect(start().disabled).toBe(true);
  });
  it('offers Human only after the saved upload options confirm actual gold', async () => {
    const { api } = await uploadMode();
    chooseFile(); chooseFile('Gold file (optional)', 'gold.json');
    expect(screen.queryByLabelText('Human score')).toBeNull();
    api.upload.mockResolvedValueOnce({ upload_id: 'gold', status: 'ready', has_gold: true, speakers: [] });
    fireEvent.click(screen.getByRole('button', { name: 'Prepare upload' }));
    expect(await screen.findByLabelText('Human score')).toBeTruthy();
    expect(api.options).toHaveBeenLastCalledWith('upload', 'gold');
    expect(checked('Human score')).toBe(false);
    fireEvent.click(screen.getByLabelText('Human score'));
    expect(screen.getByText('2 units = 1 sessions x (1 human + 1 engines x 1 combos x 1 repeats)')).toBeTruthy();
  });
  it('uses actual detected labels and samples for clinician selection before Start', async () => {
    const { api } = await uploadMode(); chooseFile();
    api.upload.mockResolvedValueOnce({ upload_id: 'plain', status: 'awaiting_speakers', has_gold: false, speakers: [{ speaker: 'Actual label', samples: ['An actual sample'] }, { speaker: 'Other label', samples: ['Another sample'] }] } as Upload);
    fireEvent.click(screen.getByRole('button', { name: 'Prepare upload' }));
    expect(await screen.findByText('An actual sample')).toBeTruthy(); expect(start().disabled).toBe(true);
    const confirm = screen.getByRole('button', { name: 'Confirm clinician' }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText('Actual label')); fireEvent.click(confirm);
    await waitFor(() => expect(api.speakers).toHaveBeenCalledWith('plain', 'Actual label'));
    await waitFor(() => expect(start().disabled).toBe(false));
  });
  it('polls a transcription until speakers are available', async () => {
    const { api } = await uploadMode(); chooseFile('Session file', 'recording.wav');
    api.upload.mockResolvedValueOnce({ upload_id: 'plain', status: 'transcribing', has_gold: false, speakers: [] });
    api.getUpload.mockResolvedValueOnce({ upload_id: 'plain', status: 'awaiting_speakers', has_gold: false, speakers: [{ speaker: 'Detected', samples: ['Sample'] }] } as Upload);
    fireEvent.click(screen.getByRole('button', { name: 'Prepare upload' }));
    expect(await screen.findByText('Transcribing recording…')).toBeTruthy();
    expect(start().disabled).toBe(true);
    expect(await screen.findByLabelText('Detected', {}, { timeout: 5000 })).toBeTruthy();
    expect(api.getUpload).toHaveBeenCalledWith('plain', expect.any(AbortSignal));
  });
  it('shows request failures, allows retry and prevents duplicate upload/start while pending', async () => {
    const { api } = await uploadMode(); chooseFile();
    let resolve!: (upload: Upload) => void;
    api.upload.mockImplementationOnce(() => new Promise<Upload>(r => { resolve = r; }));
    const prepare = screen.getByRole('button', { name: 'Prepare upload' }) as HTMLButtonElement;
    fireEvent.click(prepare); expect(prepare.disabled).toBe(true); fireEvent.click(prepare);
    expect(api.upload).toHaveBeenCalledOnce();
    resolve({ upload_id: 'plain', status: 'ready', has_gold: false, speakers: [] });
    await waitFor(() => expect(start().disabled).toBe(false));
    api.start.mockRejectedValueOnce(new Error('Please retry'));
    fireEvent.click(start());
    expect(await screen.findByRole('alert')).toBeTruthy();
    await waitFor(() => expect(start().disabled).toBe(false));
  });
  it('requires a file, goal, language and a valid optional coded portion', async () => {
    const { api } = await uploadMode();
    const prepare = screen.getByRole('button', { name: 'Prepare upload' }) as HTMLButtonElement;
    expect(prepare.disabled).toBe(true);
    chooseFile();
    fireEvent.change(screen.getByLabelText('Change goal'), { target: { value: '' } });
    expect(prepare.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Change goal'), { target: { value: 'Goal' } });
    fireEvent.click(screen.getByLabelText('Override coded portion'));
    expect(prepare.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('End'), { target: { value: '5' } });
    expect(prepare.disabled).toBe(false);
    fireEvent.click(prepare);
    await waitFor(() => expect(api.upload).toHaveBeenCalledWith(expect.objectContaining({ coded_span: { start_turn: 0, end_turn: 5 } })));
    await waitFor(() => expect(start().disabled).toBe(false));
    fireEvent.click(start());
    await waitFor(() => expect(api.start).toHaveBeenCalledWith(expect.objectContaining({ input: { upload_id: 'plain' }, change_goal: 'Goal', language: 'en', coded_span: { start_turn: 0, end_turn: 5 } })));
  });
  it('shows a failed upload, blocks Start and permits preparing it again', async () => {
    const { api } = await uploadMode(); chooseFile();
    api.upload.mockResolvedValueOnce({ upload_id: 'plain', status: 'failed', has_gold: false, speakers: [], error: { code: 'stt_failed', message: 'Recording could not be transcribed' } } as Upload);
    fireEvent.click(screen.getByRole('button', { name: 'Prepare upload' }));
    expect(await screen.findByText('Recording could not be transcribed')).toBeTruthy();
    expect(start().disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Try upload again' }));
    await waitFor(() => expect((screen.getByRole('button', { name: 'Prepare upload' }) as HTMLButtonElement).disabled).toBe(false));
  });
  it('does not submit a run twice while Start is pending', async () => {
    const { api, onRunCreated } = await mount();
    let resolve!: (run: { run_id: string; status: string }) => void;
    api.start.mockImplementationOnce(() => new Promise(r => { resolve = r; }));
    const button = start(); fireEvent.click(button); fireEvent.click(button);
    expect(button.disabled).toBe(true); expect(api.start).toHaveBeenCalledOnce();
    resolve({ run_id: 'one-run', status: 'queued' });
    await waitFor(() => expect(onRunCreated).toHaveBeenCalledOnce());
  });

  it('flags dataset sessions without gold, leaves them unselected and starts with the rest', async () => {
    const api = makeApi(); const onRunCreated = vi.fn();
    api.dataset.mockResolvedValue({ dataset_id: 'sample', title: 'Sample dataset', sessions: [{ session_id: 's1', title: 'First session', has_gold: true }, { session_id: 's2', title: 'Second session', has_gold: false }] });
    render(<NewRun api={api} onRunCreated={onRunCreated} />);
    await screen.findByLabelText('First session');
    const second = screen.getByLabelText('Second session') as HTMLInputElement;
    expect(second.disabled).toBe(true); expect(second.checked).toBe(false);
    expect(screen.getByText(/no gold file/i)).toBeTruthy();
    await waitFor(() => expect(start().disabled).toBe(false));
    fireEvent.click(start());
    await waitFor(() => expect(api.start).toHaveBeenCalledWith(expect.objectContaining({ input: { dataset_id: 'sample', session_ids: ['s1'] } })));
  });
  it('blocks Start when no dataset session has gold', async () => {
    const api = makeApi();
    api.dataset.mockResolvedValue({ dataset_id: 'sample', title: 'Sample dataset', sessions: [{ session_id: 's1', title: 'First session', has_gold: false }] });
    render(<NewRun api={api} onRunCreated={vi.fn()} />);
    await screen.findByLabelText('First session');
    expect(start().disabled).toBe(true);
  });
  it('limits the change goal to 4000 characters with a counter', async () => {
    await uploadMode();
    const goalInput = screen.getByLabelText('Change goal') as HTMLInputElement;
    expect(goalInput.maxLength).toBe(4000);
    expect(screen.getByText('14 / 4000')).toBeTruthy();
  });
  it('offers only server-allowed audio types for the session file', async () => {
    await uploadMode();
    const accept = (screen.getByLabelText('Session file') as HTMLInputElement).accept;
    expect(accept).toContain('.mp3'); expect(accept).toContain('.ogg'); expect(accept).not.toContain('audio/*');
  });
  it('shows Retry (not Reload choices) for a failed prepare and retries the action', async () => {
    const { api } = await uploadMode(); chooseFile();
    api.upload.mockRejectedValueOnce(new Error('Upload too large'));
    fireEvent.click(screen.getByRole('button', { name: 'Prepare upload' }));
    expect(await screen.findByText('Upload too large')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Reload choices' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(api.upload).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(start().disabled).toBe(false));
  });
  it('keeps polling transcription with backoff after a failed status check and shows a non-blocking error', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { api } = await uploadMode(); chooseFile('Session file', 'recording.wav');
    api.upload.mockResolvedValueOnce({ upload_id: 'plain', status: 'transcribing', has_gold: false, speakers: [] });
    api.getUpload.mockRejectedValueOnce(new Error('net down')).mockRejectedValueOnce(new Error('net down'))
      .mockResolvedValueOnce({ upload_id: 'plain', status: 'awaiting_speakers', has_gold: false, speakers: [{ speaker: 'Detected', samples: ['Sample'] }] } as Upload);
    fireEvent.click(screen.getByRole('button', { name: 'Prepare upload' }));
    await screen.findByText('Transcribing recording…');
    const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
    await advance(3000); expect(api.getUpload).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Could not check transcription status/)).toBeTruthy();
    expect(screen.getByText('Transcribing recording…')).toBeTruthy();
    await advance(3000); expect(api.getUpload).toHaveBeenCalledTimes(1);
    await advance(3100); expect(api.getUpload).toHaveBeenCalledTimes(2);
    await advance(6000); expect(api.getUpload).toHaveBeenCalledTimes(2);
    await advance(6100); expect(api.getUpload).toHaveBeenCalledTimes(3);
    expect(await screen.findByLabelText('Detected')).toBeTruthy();
    expect(screen.queryByText(/Could not check transcription status/)).toBeNull();
  });
});
