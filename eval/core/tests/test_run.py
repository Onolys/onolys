"""Comparison CLI contract; all transcript/report content is synthetic."""
import json
from types import SimpleNamespace

import pytest
from onolys_eval import cli, manifest
from onolys_eval.gold import COUNT_IDS, GLOBAL_IDS
from test_contracts import gold_data, manifest_data


def inputs(tmp_path, monkeypatch, *, span=None):
    from onolys_eval import run

    data = manifest_data()
    data['sessions'][0]['coded_span'] = span
    monkeypatch.setattr(manifest, 'load_manifest', lambda path: manifest.DatasetManifest.model_validate(data))
    monkeypatch.setattr(run, 'default_cache', lambda: tmp_path)
    session = tmp_path / 'synthetic/one'
    session.mkdir(parents=True)
    gold = gold_data()
    gold['coded_span'] = span
    (session / 'gold.json').write_text(json.dumps(gold))
    transcript = {'language': 'en', 'turns': [
        {'id': 't1', 'speaker': 'I', 'role': 'subject', 'text': 'Synthetic question?'},
        {'id': 't2', 'speaker': 'C', 'role': 'other', 'text': 'Synthetic answer.'}]}
    (session / 'transcript.json').write_text(json.dumps(transcript))
    calls = []
    monkeypatch.setattr(run, 'make_client', lambda config: calls.append(config) or object())
    monkeypatch.setattr(run, '_git_sha', lambda: 'abc123')
    monkeypatch.setattr(run, '_record_cost', lambda record: .0123)

    async def engine(ctx, tr, speakers, params):
        calls.append((ctx, tr, speakers, params))
        ctx.metrics.records.append({'input_tokens': 100, 'output_tokens': 20,
            'cache_read_tokens': 5, 'cache_write_tokens': 2, 'model': 'fake'})
        return SimpleNamespace(report={
            'behaviours': [{'item_id': key, 'onolys_count': {'mean': 1.5 if key == 'cr' else 0}}
                           for key in COUNT_IDS],
            'globals': [{'item_id': key, 'onolys': {'score': 5 if key == 'cct' else 3}}
                        for key in GLOBAL_IDS],
            'summaries': [{'item_id': 'pct_cr', 'value': 999}]})

    monkeypatch.setattr(run, 'run_miti', engine)
    return run, session, calls


def test_run_cli_table_json_and_forwarded_context(tmp_path, monkeypatch, capsys):
    _, _, calls = inputs(tmp_path, monkeypatch, span={'start_turn': 0, 'end_turn': 2})
    output = tmp_path / 'results/comparison.json'
    assert cli.main(['run', 'synthetic', 'one', '--preset', 'example', '--runs', '3',
                     '--json-out', str(output)]) == 0
    config, (ctx, transcript, speakers, params) = calls
    assert config.llm_mode == 'live' and config.preset == 'example'
    assert ctx.request_id and len(transcript.turns) == 2
    assert speakers == {'subject': 'I', 'other': 'C'}
    assert params == {'change_goal': 'Test goal', 'language': 'en', 'n_runs': 3,
                      'preset': 'example', 'coded_span': {'start_turn': 0, 'end_turn': 2}}
    text = capsys.readouterr().out
    assert 'synthetic / one' in text and 'preset=example' in text
    assert 'engine=miti sha=abc123' in text and 'tokens=127' in text and '~$0.0123' in text
    assert text.splitlines()[1].split() == ['code', 'gold', 'ours', 'diff']
    assert next(line for line in text.splitlines() if line.startswith('cr ')).split() == [
        'cr', '3', '1.5', '-1.5']
    assert 'cct (global)' in text and 'globals within 1: 3/4' in text
    assert 'count MAE 0.45' in text
    payload = json.loads(output.read_text())
    assert payload['schema'] == 'compare.v1'
    assert payload['counts']['cr']['ours'] == 1.5
    assert payload['summaries']['pct_cr']['ours'] == 1
    assert payload['metadata']['dataset_id'] == 'synthetic'
    assert payload['metadata']['session_id'] == 'one'
    assert payload['metadata']['preset'] == 'example'
    assert payload['metadata']['n_runs'] == 3
    assert payload['metadata']['git_sha'] == 'abc123'
    assert payload['metadata']['tokens'] == 127
    assert payload['metadata']['rough_cost_usd'] == .0123
    assert len(payload['notes']) == 2
    assert 'Synthetic question' not in output.read_text()


def test_defaults_and_unknown_cost_are_explicit(tmp_path, monkeypatch, capsys):
    run, _, calls = inputs(tmp_path, monkeypatch)
    monkeypatch.setattr(run, '_record_cost', lambda record: None)
    monkeypatch.setattr(run, 'default_preset_name', lambda: 'default-example')
    assert cli.main(['run', 'synthetic', 'one']) == 0
    assert calls[-1][-1]['n_runs'] == 1
    assert calls[-1][-1]['preset'] == 'default-example'
    assert 'rough cost unavailable' in capsys.readouterr().out


def test_json_out_refuses_any_git_worktree_before_model_call(tmp_path, monkeypatch):
    import subprocess
    _, _, calls = inputs(tmp_path, monkeypatch)
    other = tmp_path / 'other-repo'
    other.mkdir()
    subprocess.run(['git', 'init', '-q', str(other)], check=True)
    with pytest.raises(SystemExit) as error:
        cli.main(['run', 'synthetic', 'one', '--json-out', str(other / 'new/out.json')])
    assert error.value.code == 2
    assert calls == []
    assert not (other / 'new').exists()


def test_bucket_source_uses_exact_private_objects(tmp_path, monkeypatch, capsys):
    from google.cloud import storage
    _, session, calls = inputs(tmp_path, monkeypatch)
    objects = {'datasets/synthetic/one/' + name: (session / name).read_bytes()
               for name in ['transcript.json', 'gold.json']}
    downloaded, buckets, projects = [], [], []

    class Client:
        def bucket(self, name):
            buckets.append(name)
            return self

        def blob(self, name):
            class Blob:
                def download_as_bytes(self):
                    downloaded.append(name)
                    return objects[name]
            return Blob()

    def client(*, project):
        projects.append(project)
        return Client()

    monkeypatch.setattr(storage, 'Client', client)
    for path in session.iterdir():
        path.unlink()
    assert cli.main(['run', 'synthetic', 'one', '--source', 'bucket']) == 0
    assert projects == ['onolys']
    assert buckets == ['onolys-eval-data-staging']
    assert set(downloaded) == set(objects)
    assert len(calls) == 2
    assert not list(session.iterdir())


@pytest.mark.parametrize('problem', ['identity', 'warnings', 'span', 'speaker'])
def test_bad_input_fails_before_client_creation(tmp_path, monkeypatch, problem):
    _, session, calls = inputs(tmp_path, monkeypatch)
    gold = json.loads((session / 'gold.json').read_text())
    if problem == 'identity':
        gold['session_id'] = 'wrong'
    elif problem == 'warnings':
        gold['parse']['warnings'] = ['unresolved']
    elif problem == 'span':
        gold['coded_span'] = {'start_turn': 0, 'end_turn': 2}
    else:
        path = session / 'transcript.json'
        transcript = json.loads(path.read_text())
        transcript['turns'][0]['speaker'] = 'unknown'
        path.write_text(json.dumps(transcript))
    (session / 'gold.json').write_text(json.dumps(gold))
    with pytest.raises(SystemExit) as error:
        cli.main(['run', 'synthetic', 'one'])
    assert error.value.code == 2
    assert calls == []


@pytest.mark.parametrize('arguments', [['--runs', '0'], ['--runs', '-1'], ['--source', 'other']])
def test_invalid_arguments(arguments):
    with pytest.raises(SystemExit) as error:
        cli.main(['run', 'synthetic', 'one', *arguments])
    assert error.value.code == 2


def test_rough_cost_preserves_cached_usage_and_unknown_prices(monkeypatch):
    import sys

    from onolys_eval.run import _record_cost

    calls = []

    def price(**kwargs):
        calls.append(kwargs)
        if kwargs['model'] == 'unpriced':
            raise ValueError('No local pricing')
        return .1, .2

    monkeypatch.setitem(sys.modules, 'litellm', SimpleNamespace(cost_per_token=price))
    record = {'model': 'priced', 'input_tokens': 100, 'output_tokens': 20,
              'cache_read_tokens': 5, 'cache_write_tokens': 2}
    assert _record_cost(record) == pytest.approx(.3)
    # Metrics input_tokens is LiteLLM prompt_tokens, already inclusive of caches.
    assert calls[0] == {'model': 'priced', 'prompt_tokens': 100, 'completion_tokens': 20,
                        'cache_read_input_tokens': 5, 'cache_creation_input_tokens': 2}
    assert _record_cost({**record, 'model': 'unpriced'}) is None
