"""Run the lean engine against reference gold without exporting session content."""
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from onolys_miti.context import RunContext
from onolys_miti.llm import LLMConfig, MetricsCollector, make_client
from onolys_miti.llm.routes import default_preset_name
from onolys_miti.run import run_miti
from onolys_miti.transcript import Transcript

from .adapters import miti_lean_scores
from .fetch import default_cache, require_external_path
from .gold import Gold
from .manifest import DatasetManifest
from .metrics import Scores, compare
from .upload import BUCKET

_TOKEN_KEYS = ('input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens')


def _git_sha() -> str:
    result = subprocess.run(
        ['git', '-C', str(Path(__file__).resolve().parent), 'rev-parse', 'HEAD'],
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else 'unknown'


def _record_cost(record: dict) -> float | None:
    """Local LiteLLM rates are a rough estimate, never a billing guarantee."""
    from litellm import cost_per_token

    try:
        input_cost, output_cost = cost_per_token(
            model=record['model'],
            prompt_tokens=record.get('input_tokens', 0),
            completion_tokens=record.get('output_tokens', 0),
            cache_read_input_tokens=record.get('cache_read_tokens', 0),
            cache_creation_input_tokens=record.get('cache_write_tokens', 0),
        )
        return input_cost + output_cost
    except Exception:  # noqa: BLE001 - missing prices must not discard a completed comparison.
        return None


def _load_inputs(manifest, session, source):
    if source == 'bucket':
        from google.cloud import storage

        bucket = storage.Client(project='onolys').bucket(BUCKET)
        prefix = f'datasets/{manifest.dataset_id}/{session.session_id}/'
        transcript_data = bucket.blob(prefix + 'transcript.json').download_as_bytes()
        gold_data = bucket.blob(prefix + 'gold.json').download_as_bytes()
    elif source == 'cache':
        directory = default_cache() / manifest.dataset_id / session.session_id
        transcript_data = require_external_path(directory / 'transcript.json').read_bytes()
        gold_data = require_external_path(directory / 'gold.json').read_bytes()
    else:
        raise ValueError(f'Unknown source: {source}')
    transcript = Transcript.model_validate_json(transcript_data)
    gold = Gold.model_validate_json(gold_data)
    if (gold.dataset_id, gold.session_id) != (manifest.dataset_id, session.session_id):
        raise ValueError('Gold identity does not match the requested dataset/session')
    if gold.parse.warnings:
        raise ValueError('Gold has unresolved conversion warnings; run convert first')
    if gold.coded_span != session.coded_span:
        raise ValueError('Manifest and gold coded spans differ; run convert first')
    return transcript, gold


def _speaker_map(transcript, session):
    observed = {turn.speaker for turn in transcript.turns}
    clinicians = observed.intersection(session.clinician_labels)
    if len(clinicians) != 1:
        raise ValueError('Expected exactly one observed clinician speaker')
    if None in observed or '' in observed:
        raise ValueError('Every turn must have an observed speaker label')
    others = observed - clinicians
    mapping = {'subject': next(iter(clinicians))}
    if len(others) == 1:
        mapping['other'] = next(iter(others))
    return mapping


def _number(value) -> str:
    return 'null' if value is None else f'{value:.4g}'


def _table(comparison, metadata) -> str:
    cost = metadata['rough_cost_usd']
    price = 'rough cost unavailable' if cost is None else f'~${cost:.4f} (rough)'
    lines = [
        (f"{metadata['dataset_id']} / {metadata['session_id']}   preset={metadata['preset']}   "
         f"engine=miti sha={metadata['git_sha']}   tokens={metadata['tokens']} {price}"),
        f"{'code':27} {'gold':>8} {'ours':>8} {'diff':>8}",
    ]
    for group in ('counts', 'globals', 'summaries'):
        for key, row in comparison[group].items():
            label = key + (' (global)' if group == 'globals' else '')
            lines.append(f"{label:27} {_number(row['gold']):>8} {_number(row['ours']):>8} "
                         f"{_number(row['diff']):>8}")
    mae = sum(row['abs_diff'] for row in comparison['counts'].values()) / len(comparison['counts'])
    within = sum(row['abs_diff'] <= 1 for row in comparison['globals'].values())
    lines.append(f'count MAE {_number(mae)} | globals within 1: {within}/4')
    lines.extend('Note: ' + note for note in comparison['notes'])
    return '\n'.join(lines)


async def run_session(
    manifest: DatasetManifest, session_id: str, *, preset: str | None = None,
    n_runs: int = 1, source: str = 'cache', json_out: Path | None = None,
) -> dict:
    """Complete one comparison; accuracy is descriptive, never an exit threshold.

    Span forwarding uses the SP1 run_miti contract (merged at integration). The
    CASAA manifest uses full sessions. No speaker identification call is needed.
    """
    if n_runs < 1:
        raise ValueError('runs must be at least 1')
    output = require_external_path(json_out) if json_out is not None else None
    session = next((s for s in manifest.sessions if s.session_id == session_id), None)
    if session is None:
        raise ValueError(f'Unknown session: {session_id}')
    transcript, gold = _load_inputs(manifest, session, source)
    speaker_map = _speaker_map(transcript, session)
    preset = preset or default_preset_name()
    metrics = MetricsCollector()
    ctx = RunContext(llm=make_client(LLMConfig(llm_mode='live', preset=preset)),
                     metrics=metrics, request_id=f'eval-{uuid4().hex}')
    result = await run_miti(ctx, transcript, speaker_map, {
        'change_goal': session.change_goal, 'language': transcript.language or 'en',
        'n_runs': n_runs, 'preset': preset,
        'coded_span': session.coded_span.model_dump() if session.coded_span else None,
    })
    comparison = compare(Scores(counts=gold.counts, globals=gold.globals),
                         miti_lean_scores(result.report))
    costs = [_record_cost(record) for record in metrics.records]
    metadata = {
        'dataset_id': manifest.dataset_id, 'session_id': session_id, 'preset': preset,
        'engine': 'miti', 'git_sha': _git_sha(), 'n_runs': n_runs, 'source': source,
        'request_id': ctx.request_id, 'completed_at': datetime.now(UTC).isoformat(),
        'coded_span': session.coded_span.model_dump() if session.coded_span else None,
        'tokens': sum(record.get(key, 0) for record in metrics.records for key in _TOKEN_KEYS),
        'rough_cost_usd': sum(costs) if all(cost is not None for cost in costs) else None,
        'cost_basis': 'rough estimate from local LiteLLM rates; unavailable for unknown prices',
    }
    payload = {**comparison, 'metadata': metadata}
    if output is not None:
        # Recheck immediately before writing, including any newly created symlinks.
        output = require_external_path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n')
    print(_table(comparison, metadata))
    return payload
