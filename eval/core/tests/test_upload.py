"""Upload preflight and exact private bucket layout, using synthetic assets only."""
import json
from copy import deepcopy

import pytest
from onolys_eval.manifest import DatasetManifest
from onolys_eval.upload import upload_dataset
from test_contracts import gold_data, manifest_data


class FakeClient:
    def __init__(self):
        self.objects = {}
        self.buckets = []

    def bucket(self, name):
        self.buckets.append(name)
        return self

    def blob(self, name):
        objects = self.objects

        class Blob:
            def upload_from_filename(self, filename, *, content_type):
                from pathlib import Path
                objects[name] = (Path(filename).read_bytes(), content_type)

            def upload_from_string(self, data, *, content_type):
                objects[name] = (data.encode(), content_type)
        return Blob()


def dataset(tmp_path, *, audio=False, second=False):
    data = manifest_data()
    if audio:
        data['sessions'][0]['audio_url'] = 'https://example.org/audio.mp3'
    if second:
        extra = deepcopy(data['sessions'][0])
        extra['session_id'] = 'two'
        data['sessions'].append(extra)
    manifest = DatasetManifest.model_validate(data)
    for session in manifest.sessions:
        converted = tmp_path / 'synthetic' / session.session_id
        converted.mkdir(parents=True)
        gold = gold_data()
        gold['session_id'] = session.session_id
        (converted / 'gold.json').write_text(json.dumps(gold))
        (converted / 'transcript.json').write_text('{"language":"en","turns":[]}')
        raw = tmp_path / 'synthetic/raw' / session.session_id
        raw.mkdir(parents=True)
        for name in ['coded.pdf', 'uncoded.pdf'] + (['audio.mp3'] if audio else []):
            (raw / name).write_bytes(b'synthetic')
    return manifest


def test_exact_layout_and_rendered_manifest(tmp_path):
    manifest = dataset(tmp_path, audio=True)
    client = FakeClient()
    assert upload_dataset(manifest, tmp_path, client=client) == 6
    prefix = 'datasets/synthetic/'
    assert client.buckets == ['onolys-eval-data-staging']
    assert set(client.objects) == {prefix + name for name in [
        'manifest.json', 'one/transcript.json', 'one/gold.json',
        'one/raw/coded.pdf', 'one/raw/uncoded.pdf', 'one/raw/audio.mp3']}
    assert json.loads(client.objects[prefix + 'manifest.json'][0]) == manifest.model_dump(mode='json')
    assert client.objects[prefix + 'one/raw/audio.mp3'][1] == 'audio/mpeg'


@pytest.mark.parametrize('problem', ['warnings', 'missing', 'wrong_identity', 'invalid_gold'])
def test_preflight_entire_dataset_before_any_cloud_write(tmp_path, problem):
    manifest = dataset(tmp_path, second=True)
    path = tmp_path / 'synthetic/two/gold.json'
    gold = json.loads(path.read_text())
    if problem == 'warnings':
        gold['parse']['warnings'] = ['unresolved token']
    elif problem == 'missing':
        (tmp_path / 'synthetic/raw/two/coded.pdf').unlink()
    elif problem == 'wrong_identity':
        gold['session_id'] = 'other'
    else:
        del gold['parse']
    path.write_text(json.dumps(gold))
    client = FakeClient()
    with pytest.raises((ValueError, OSError)):
        upload_dataset(manifest, tmp_path, client=client)
    assert client.objects == {}
    assert client.buckets == []


def test_upload_cli_dispatches(tmp_path, monkeypatch, capsys):
    from onolys_eval import cli, upload
    called = []
    monkeypatch.setattr(upload, 'upload_dataset', lambda manifest, cache: called.append(
        (manifest.dataset_id, cache)) or 33)
    assert cli.main(['upload', 'casaa-miti421-video2013', '--cache', str(tmp_path)]) == 0
    assert called == [('casaa-miti421-video2013', tmp_path)]
    assert '33 objects' in capsys.readouterr().out


def test_adc_client_uses_staging_project_when_adc_has_no_default_project(tmp_path, monkeypatch):
    from google.cloud import storage

    manifest = dataset(tmp_path)
    client = FakeClient()
    projects = []

    def make_client(*, project):
        projects.append(project)
        return client

    monkeypatch.setattr(storage, 'Client', make_client)
    assert upload_dataset(manifest, tmp_path) == 5
    assert projects == ['onolys']
