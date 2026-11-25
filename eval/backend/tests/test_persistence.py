import json
from pathlib import Path

import pytest
from onolys_engine_core.engine import RunUsage

from onolys_eval_backend.costs import PriceBook
from onolys_eval_backend.repository import InMemoryEvalRepository
from onolys_eval_backend.storage import InMemoryBucket


def test_bucket_layout():
    bucket = InMemoryBucket()
    bucket.write_json('datasets/reference/s1/transcript.json', {'turns': []})
    bucket.write_bytes('uploads/u/input.txt', b'Client: hi', content_type='text/plain')
    assert bucket.read_json('datasets/reference/s1/transcript.json') == {'turns': []}
    assert bucket.list('datasets/') == ['datasets/reference/s1/transcript.json']
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
           'status': 'queued', 'usage': {'input_tokens': 10}}
    repo.create_group('r', run)
    repo.create_group('newer', {**run, 'created_at': '2026-11-24T00:00:00Z'})
    assert repo.get_run('r') == run
    assert list(repo.list_runs(limit=1)) == ['newer']
    run['usage']['input_tokens'] = 900
    assert repo.get_run('r')['usage']['input_tokens'] == 10
    with pytest.raises(ValueError):
        repo.create_group('r', {})
    repo.delete_run('r')
    repo.delete_run('r')  # idempotent
    assert repo.get_run('r') is None


def test_cancel_run_sets_flags_once_and_ignores_terminal_runs():
    repo = InMemoryEvalRepository()
    repo.create_group('done', {'status': 'done'})
    assert repo.cancel_run('done')  # found, but a no-op
    assert 'cancel_requested' not in repo.get_run('done')
    repo.create_group('live', {'status': 'running'})
    assert repo.cancel_run('live', at='T') and repo.cancel_run('live', at='later')
    assert repo.get_run('live')['cancel_requested'] is True
    assert repo.get_run('live')['cancelled_at'] == 'T'  # set once
    assert not repo.cancel_run('absent')


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
def test_firestore_pagination_survives_deleted_cursor():
    import os
    from uuid import uuid4

    from google.cloud import firestore

    from onolys_eval_backend.repository import FirestoreEvalRepository

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
            repo.create_group(rid, {"created_at": "2026-01-01", "status": "running"})
        page, more = repo.list_runs_page(1)
        assert list(page) == ["c"] and more
        repo.runs.document("c").delete()
        page, more = repo.list_runs_page(1, ("2026-01-01", "c"))
        assert list(page) == ["b"] and more
    finally:
        for doc in repo.runs.stream():
            doc.reference.delete()
        client.close()
