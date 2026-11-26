/** Plain-language catalog for the error CODE stored on a failed unit. Only the code is stored (full messages are never kept: PHI policy), so every explanation is keyed by code.
 * Sources: public API codes (api/src/onolys_api/errors.py, adapters/error_map.py) and eval scheduler codes (eval/backend eval_scheduler.py, eval_view.py). */
export interface ErrorEntry { title: string; explanation: string; fix: string }
export interface ErrorInfo extends ErrorEntry { code: string; known: boolean }

const e = (title: string, explanation: string, fix: string): ErrorEntry => ({ title, explanation, fix });

export const ERROR_CATALOG: Readonly<Record<string, ErrorEntry>> = {
  invalid_parameters: e('Invalid parameters',
    'The engine rejected the parameters this unit was run with. It usually means the run params did not match what the engine accepts (recent example: the one-shot engine rejected an extra stt_run param, fixed in PR #77).',
    'Check the run config and the engine version, then rerun. If it keeps failing, search the logs for the unit.'),
  provider_unavailable: e('Provider unavailable',
    'The model provider was failing or busy, so this unit was skipped or could not be started.',
    'Wait a few minutes and rerun the failed units.'),
  provider_error: e('Provider error',
    'The model provider returned an error while this unit was running.',
    'Rerun the unit. If it repeats, check the provider status and the unit logs.'),
  provider_skipped: e('Skipped after provider failures',
    'This provider failed repeatedly in this run, so its remaining units were skipped.',
    'Rerun once the provider recovers.'),
  upstream_unavailable: e('Service unavailable',
    'A service this unit depends on was unavailable.',
    'Run again shortly.'),
  rate_limited: e('Rate limited',
    'The provider or API refused the request because there were too many in a short time.',
    'Wait a few minutes, then rerun. Lower concurrency if it keeps happening.'),
  timeout: e('Timed out',
    'The unit took longer than the allowed time and was stopped.',
    'Rerun. If it repeats, try a smaller session or a faster model or effort.'),
  deadline_exceeded: e('Deadline exceeded',
    'The unit ran past its deadline and was stopped.',
    'Rerun. If it repeats, try a smaller session or a faster model or effort.'),
  internal_error: e('Internal error',
    'Something went wrong on our side while running this unit.',
    'Rerun. If it repeats, open the unit logs and report the unit id.'),
  output_invalid: e('Invalid engine output',
    'The engine returned an answer that did not match its expected schema.',
    'Rerun. If it repeats, check the unit logs for the model and engine version.'),
  invalid_coded_span: e('Invalid coded span',
    'The coded span does not fit inside the transcript, or time spans were used without timestamps.',
    'Choose a valid span within the transcript and start a new run.'),
  session_too_long: e('Session too long',
    'The coded portion is over the limit (25 minutes or 6000 words).',
    'Use a narrower coded span and start a new run.'),
  transcription_failed: e('Transcription failed',
    'The recording could not be transcribed.',
    'Upload a different file, or use a transcript.'),
  no_speech: e('No speech found',
    'No usable speech was found in the recording.',
    'Check the recording has audible speech, or upload a different file.'),
  speakers_not_separated: e('Speakers not separated',
    'The speakers could not be told apart in the recording.',
    'Use a recording with clearer separate speakers, or upload a transcript.'),
  enqueue_failed: e('Could not start',
    'The run could not be queued for the worker, so it never started.',
    'Start the run again.'),
  execution_config_changed: e('Config changed during run',
    'The engine or model setup changed after this run was saved, so this unit was not run with the saved config.',
    'Start a new run with the current config.'),
  cancelled: e('Cancelled',
    'The run was cancelled before this unit finished.',
    'Rerun the run if you still need these units.'),
  gold_unavailable: e('Human reference unavailable',
    'The human reference for this session could not be loaded.',
    'Check the dataset session has a human reference, then rerun.'),
  unknown: e('Unknown error',
    'The unit failed but no error code was recorded.',
    'Open the unit logs to see what happened.'),
};

export const KNOWN_ERROR_CODES = Object.keys(ERROR_CATALOG);

const GENERIC_FIX = 'Rerun the unit. If it repeats, open the unit logs and report the unit id.';

/** Catalog entry for a stored code. Unknown codes show the code verbatim; empty or missing codes give a generic entry. */
export function describeError(code: string | null | undefined): ErrorInfo {
  const c = (code ?? '').trim();
  if (!c) return { code: '', known: false, title: 'Unknown error', explanation: 'No error code was recorded for this unit.', fix: GENERIC_FIX };
  if (Object.hasOwn(ERROR_CATALOG, c)) return { code: c, known: true, ...ERROR_CATALOG[c] };
  return { code: c, known: false, title: c, explanation: 'This error code is not recognised in the catalog yet.', fix: GENERIC_FIX };
}
