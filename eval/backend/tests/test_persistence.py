import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from onolys_engine_core.engine import RunUsage

from onolys_eval_backend.costs import PriceBook
from onolys_eval_backend.repository import InMemoryEvalRepository
from onolys_eval_backend.storage import (
    INLINE_OUTPUT_LIMIT,
    InMemoryBucket,
    load_output,
    store_output,
)


def test_bucket_layout_and_output_boundary():
    bucket = InMemoryBucket()
    bucket.write_json('datasets/reference/s1/transcript.json', {'turns': []})
    bucket.write_bytes('uploads/u/input.txt', b'Client: hi', content_type='text/plain')
    assert bucket.read_json('datasets/reference/s1/transcript.json') == {'turns': []}
    assert bucket.list('datasets/') == ['datasets/reference/s1/transcript.json']
    # UTF-8 serialized size, rather than character count, controls the limit.
    small = {'text': 'x' * (INLINE_OUTPUT_LIMIT - len(b'{"text":""}'))}
    assert len(json.dumps(small, separators=(',', ':')).encode()) == INLINE_OUTPUT_LIMIT
    inline = store_output(bucket, 'r', 's', small)
    assert inline == {'output': small, 'output_ref': None}
    large = {'text': 'é' * INLINE_OUTPUT_LIMIT}
    spilled = store_output(bucket, 'r', 'l', large)
    assert spilled == {'output': None, 'output_ref': 'runs/r/l.json'}
    assert load_output(bucket, spilled) == large
    assert load_output(bucket, inline) == small
    with pytest.raises(FileNotFoundError):
        bucket.read_bytes('missing')


def test_repository_roundtrip_and_isolation():
    repo = InMemoryEvalRepository()
    upload = {'name': 'session.txt', 'kind': 'text', 'paths': {'input': 'uploads/u/input.txt'},
              'has_gold': False, 'created_by': 'user', 'created_at': '2026-11-23T00:00:00Z'}
    repo.create_upload('u', upload)
    assert repo.get_upload('u') == upload
    repo.update_upload('u', {'status': 'ready'})
    assert repo.get_upload('u')['status'] == 'ready'
    run = {'input': {'upload_id': 'u'}, 'created_at': '2026-11-23T00:00:00Z',
           'engine_git_shas': {'miti': 'sha'}, 'engine_versions': {'miti': '1'},
           'resolved_models': {'default': {'mid': 'model'}}, 'status': 'queued'}
    unit = {'session': 'u', 'engine': 'miti', 'preset': 'default', 'repeat': 0,
            'status': 'queued', 'stage': None, 'error_code': None, 'scores': None,
            'run_info': {'usage': {'input_tokens': 10}}, 'output': {'ok': True}}
    repo.create_run('r', run, {'one': unit})
    repo.create_run('newer', {**run, 'created_at': '2026-11-24T00:00:00Z'}, {})
    assert repo.get_run('r') == run
    assert repo.get_unit('r', 'one') == unit
    assert repo.list_units('r') == {'one': unit}
    assert list(repo.list_runs(limit=1)) == ['newer']
    unit['run_info']['usage']['input_tokens'] = 900
    assert repo.get_unit('r', 'one')['run_info']['usage']['input_tokens'] == 10
    with pytest.raises(ValueError):
        repo.create_run('r', {}, {})
    with pytest.raises(KeyError):
        repo.update_unit('r', 'absent', {'status': 'done'})


def test_atomic_transaction_supports_claim_and_finalization():
    repo = InMemoryEvalRepository()
    repo.create_run('r', {'status': 'queued', 'completed_units': 0}, {'u': {'status': 'queued'}})

    def claim(_):
        def mutate(run, unit):
            if run.get('cancel_requested') or unit['status'] != 'queued':
                return None
            return ({'status': 'running'}, {'status': 'running'})
        return repo.transact_unit('r', 'u', mutate)

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(claim, range(30))) == 1
    def finish(run, unit):
        assert unit['status'] == 'running'
        return ({'status': 'done', 'completed_units': run['completed_units'] + 1},
                {'status': 'done', 'scores': {'counts': {}}})
    assert repo.transact_unit('r', 'u', finish)
    assert repo.get_run('r')['completed_units'] == 1
    assert repo.get_unit('r', 'u')['status'] == 'done'
    assert repo.cancel_run('r')
    assert repo.get_run('r')['cancel_requested'] is True


def test_prices_prefer_provider_zero_and_token_fallback(tmp_path):
    path = tmp_path / 'prices.yaml'
    path.write_text('models:\n  provider/model:\n    input_usd_per_million: 2\n'
                    '    output_usd_per_million: 8\n    rate_as_of: "2026-11-23"\n'
                    '    source: "test fixture, not a real provider rate"\n')
    prices = PriceBook.from_yaml(path)
    assert prices.estimate(RunUsage(input_tokens=100, output_tokens=20, calls=1, cost_usd=0),
                           'unknown').cost_usd == 0
    exact = prices.estimate({'input_tokens': 1, 'output_tokens': 2, 'cost_usd': 1.23}, 'unknown')
    assert exact.cost_usd == 1.23 and exact.is_estimate is False
    fallback = prices.estimate({'input_tokens': 1000000, 'output_tokens': 500000,
                               'cache_read_tokens': 300000}, 'provider/model')
    assert fallback.cost_usd == 6 and fallback.is_estimate
    assert prices.estimate({'input_tokens': 1, 'output_tokens': 1}, 'unknown').cost_usd is None
    bundled = PriceBook.from_yaml()
    assert bundled.estimate({'input_tokens': 1}, 'gemini/gemini-4-neon').cost_usd is None
    known = bundled.estimate({'input_tokens': 1000000, 'output_tokens': 1000000},
                             'anthropic/claude-sonnet-5-5')
    assert known.cost_usd == 12 and known.is_estimate
    assert 'LiteLLM 1.110.2' in known.source


def test_firestore_rules_remain_denied_and_history_index():
    root = Path(__file__).resolve().parents[3]
    rules = (root / 'firestore.rules').read_text()
    assert 'eval_uploads' in rules and 'eval_runs' in rules
    assert 'match /eval_' not in rules
    assert 'allow read, write: if false;' in rules
    indexes = json.loads((root / 'api/firestore.indexes.json').read_text())
    assert any(i['collectionGroup'] == 'eval_runs' and i['fieldPath'] == 'created_at'
               and {'order': 'DESCENDING', 'queryScope': 'COLLECTION'} in i['indexes']
               for i in indexes['fieldOverrides'])


def test_gcs_adapter_uses_injected_bucket():
    from unittest.mock import Mock

    from google.api_core.exceptions import NotFound

    from onolys_eval_backend.storage import GCSBucket

    remote = Mock()
    remote.blob.return_value.download_as_bytes.return_value = b'{"ok":true}'
    remote.list_blobs.return_value = [Mock(name='unused')]
    remote.list_blobs.return_value[0].name = 'datasets/example/manifest.json'
    bucket = GCSBucket(remote)
    assert bucket.read_json('datasets/example/manifest.json') == {'ok': True}
    assert bucket.list('datasets/') == ['datasets/example/manifest.json']
    bucket.write_json('uploads/u/transcript.json', {'turns': []})
    remote.blob.return_value.upload_from_string.assert_called_once_with(
        b'{"turns":[]}', content_type='application/json')
    remote.blob.return_value.download_as_bytes.side_effect = NotFound('missing')
    with pytest.raises(FileNotFoundError):
        bucket.read_bytes('missing')


def test_firestore_adapter_transaction_reads_both_before_writing(monkeypatch):
    from unittest.mock import Mock

    from google.cloud import firestore

    from onolys_eval_backend.repository import FirestoreEvalRepository

    # Exercise repository transaction body without credentials or RPCs. The SDK's
    # decorator supplies retries in production; this test checks our read/write order.
    monkeypatch.setattr(firestore, 'transactional', lambda fn: fn)
    client = Mock()
    run_ref = client.collection.return_value.document.return_value
    unit_ref = run_ref.collection.return_value.document.return_value
    run_ref.get.return_value = Mock(exists=True)
    run_ref.get.return_value.to_dict.return_value = {'completed_units': 0}
    unit_ref.get.return_value = Mock(exists=True)
    unit_ref.get.return_value.to_dict.return_value = {'status': 'running'}
    transaction = client.transaction.return_value
    events = []
    run_ref.get.side_effect = lambda **kw: events.append('run_read') or run_ref.get.return_value
    unit_ref.get.side_effect = lambda **kw: events.append('unit_read') or unit_ref.get.return_value
    transaction.update.side_effect = lambda ref, patch: events.append(('write', patch))
    repo = FirestoreEvalRepository(client)
    assert repo.transact_unit('r', 'u', lambda run, unit: (
        {'completed_units': run['completed_units'] + 1}, {'status': 'done'}))
    assert events == ['run_read', 'unit_read', ('write', {'completed_units': 1}),
                      ('write', {'status': 'done'})]
    events.clear()
    assert not repo.transact_unit('r', 'u', lambda run, unit: None)
    assert events == ['run_read', 'unit_read']
    repo.create_run('r', {'status': 'queued'}, {'u': {'status': 'queued'}})
    assert client.batch.return_value.create.call_count == 2
    client.batch.return_value.commit.assert_called_once_with()


def test_attempt_output_paths_keep_reclaimed_results_independent(monkeypatch):
    from onolys_eval_backend import storage

    monkeypatch.setattr(storage, "INLINE_OUTPUT_LIMIT", 1)
    bucket = InMemoryBucket()
    current = store_output(bucket, "run", "unit", {"result": "current"}, attempt="new")
    store_output(bucket, "run", "unit", {"result": "stale"}, attempt="old")
    assert load_output(bucket, current) == {"result": "current"}


def test_named_queue_task_deduplicates_accepted_retry():
    from types import SimpleNamespace

    from google.api_core.exceptions import AlreadyExists
    from test_app import ENV

    from onolys_eval_backend.config import EvalConfig
    from onolys_eval_backend.queue import CloudTasksQueue

    calls = []

    def create_task(**kwargs):
        calls.append(kwargs)
        raise AlreadyExists("task already accepted")

    queue = CloudTasksQueue(EvalConfig.from_env(ENV), SimpleNamespace(create_task=create_task))
    queue.enqueue("transcribe", {"upload_id": "saved"}, task_id="upload-saved")
    assert calls[0]["task"]["name"].endswith("/tasks/upload-saved")
    with pytest.raises(AlreadyExists):
        queue.enqueue("transcribe", {"upload_id": "saved"})


@pytest.mark.live
def test_firestore_pagination_survives_deleted_cursor_and_fences_completion():
    import os
    from uuid import uuid4

    from google.cloud import firestore

    from onolys_eval_backend.repository import FirestoreEvalRepository
    from onolys_eval_backend.runs import finish_unit

    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        pytest.skip("Firestore emulator required")
    client = firestore.Client(project="demo-test")
    repo = FirestoreEvalRepository(client)
    repo.runs = client.collection(f"eval_t13_{uuid4().hex}")
    try:
        upload_id = uuid4().hex
        repo.create_upload(upload_id, {"status": "awaiting_upload"})
        assert repo.transition_upload(upload_id, "awaiting_upload", {"status": "transcribing"})
        assert not repo.transition_upload(upload_id, "awaiting_upload", {"status": "failed"})
        assert repo.get_upload(upload_id)["status"] == "transcribing"
        repo.uploads.document(upload_id).delete()
        for rid in ("a", "b", "c"):
            repo.create_run(rid, {"created_at": "2026-01-01", "completed_units": 0,
                                 "total_units": 1, "done_units": 0, "failed_units": 0,
                                 "cancelled_units": 0, "usage": {}, "cost_usd_est": 0},
                            {"u": {"status": "running", "lease_owner": "new"}})
        page, more = repo.list_runs_page(1)
        assert list(page) == ["c"] and more
        repo.runs.document("c").delete()
        page, more = repo.list_runs_page(1, ("2026-01-01", "c"))
        assert list(page) == ["b"] and more
        assert not finish_unit(repo, "a", "u", {"status": "done"}, owner="old")
        assert finish_unit(repo, "a", "u", {"status": "done"}, owner="new")
        assert not finish_unit(repo, "a", "u", {"status": "done"}, owner="new")
        assert repo.get_run("a")["completed_units"] == 1
    finally:
        for doc in repo.runs.stream():
            for unit in doc.reference.collection("units").stream():
                unit.reference.delete()
            doc.reference.delete()
        client.close()
