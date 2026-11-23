// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NewRun, plannedUnits } from './NewRun';
import type { EvalApi, Options, Upload } from './api';

afterEach(() => { cleanup(); vi.useRealTimers(); });
const options: Options = {
  engines: [{ id: 'human', engine: 'human', label: 'Human score', prod: false }, { id: 'miti', engine: 'miti', label: 'MITI lean', prod: true }, { id: 'oneshot:miti', engine: 'oneshot', config: 'miti', label: 'One-shot · MITI', prod: false }],
  presets: [{ name: 'configured', prod: true, models: {} }, { name: 'other', prod: false, models: {} }],
  defaults: { dataset: { engines: ['human', 'miti'], presets: ['configured'] }, upload: { engines: ['miti'], presets: ['configured'] } },
};
function makeApi() {
  return {
    me: vi.fn().mockResolvedValue({}),
    options: vi.fn(async (_mode: string, uploadId?: string) => ({ ...options, engines: uploadId === 'gold' || _mode === 'dataset' ? options.engines : options.engines.filter(e => e.id !== 'human') })),
    datasets: vi.fn().mockResolvedValue({ datasets: [{ dataset_id: 'sample', title: 'Sample dataset' }] }),
    dataset: vi.fn().mockResolvedValue({ dataset_id: 'sample', title: 'Sample dataset', sessions: [{ session_id: 's1', title: 'First session' }, { session_id: 's2', title: 'Second session' }] }),
    upload: vi.fn().mockResolvedValue({ upload_id: 'plain', status: 'ready', has_gold: false, speakers: [] }),
    getUpload: vi.fn().mockResolvedValue({ upload_id: 'plain', status: 'ready', has_gold: false, speakers: [] }),
    speakers: vi.fn().mockResolvedValue({ upload_id: 'plain', status: 'ready', has_gold: false, speakers: [] }),
    start: vi.fn().mockResolvedValue({ run_id: 'run-1', status: 'queued' }),
  } satisfies EvalApi;
}
async function mount() {
  const api = makeApi(); const onRunCreated = vi.fn();
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
  it('loads configured dataset defaults, all sessions, prod labels and starts with wire IDs', async () => {
    const { api, onRunCreated } = await mount();
    expect(checked('First session')).toBe(true); expect(checked('Second session')).toBe(true);
    expect(checked('Human score')).toBe(true); expect(checked('MITI lean (prod)')).toBe(true);
    expect(checked('configured (prod)')).toBe(true);
    expect(screen.getByText('4 planned units')).toBeTruthy();
    fireEvent.click(start());
    await waitFor(() => expect(api.start).toHaveBeenCalledWith({ input: { dataset_id: 'sample', session_ids: ['s1', 's2'] }, engines: ['human', 'miti'], presets: ['configured'], repeats: 1 }));
    expect(onRunCreated).toHaveBeenCalledWith('run-1');
  });
  it('counts Human once per session and excludes its preset/repeat axes', async () => {
    await mount();
    fireEvent.click(screen.getByLabelText('One-shot · MITI')); fireEvent.click(screen.getByLabelText('other'));
    fireEvent.change(screen.getByLabelText('Runs per cell'), { target: { value: '3' } });
    expect(screen.getByText('26 planned units')).toBeTruthy();
    expect(plannedUnits(8, ['human', 'miti'], ['a', 'b'], 3)).toBe(56);
    fireEvent.click(screen.getByLabelText('MITI lean (prod)')); fireEvent.click(screen.getByLabelText('One-shot · MITI'));
    fireEvent.click(screen.getByLabelText('configured (prod)')); fireEvent.click(screen.getByLabelText('other'));
    expect(screen.getByText('2 planned units')).toBeTruthy(); expect(start().disabled).toBe(false);
    fireEvent.click(screen.getByLabelText('Human score')); expect(start().disabled).toBe(true);
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
    expect(screen.getByText('2 planned units')).toBeTruthy();
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

});
