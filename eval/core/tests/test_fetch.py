"""Synthetic downloads only; source datasets remain outside git."""
import hashlib
import io
import json
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.error import URLError

import pytest
from onolys_eval import cli
from onolys_eval.fetch import default_cache, fetch_dataset
from onolys_eval.manifest import DatasetManifest
from test_contracts import manifest_data


@pytest.fixture
def dataset():
    data = manifest_data()
    data["sessions"][0]["audio_url"] = "https://example.org/audio.mp3"
    return DatasetManifest.model_validate(data)


def test_fetch_layout_hashes_and_second_run_skips(tmp_path, monkeypatch, dataset):
    calls = []

    def download(url, **kwargs):
        calls.append(url)
        return io.BytesIO(url.encode())

    monkeypatch.setattr("onolys_eval.fetch.urlopen", download)
    raw = fetch_dataset(dataset, tmp_path / "cache")
    assert raw == tmp_path / "cache/synthetic/raw"
    metadata = json.loads((raw / "fetch.json").read_text())
    assert metadata["dataset_id"] == "synthetic"
    assert set(metadata["files"]) == {"one/coded.pdf", "one/uncoded.pdf", "one/audio.mp3"}
    for relative, info in metadata["files"].items():
        payload = (raw / relative).read_bytes()
        assert payload == info["url"].encode()
        assert info["sha256"] == hashlib.sha256(payload).hexdigest()
        assert datetime.fromisoformat(info["retrieved_at"]).utcoffset().total_seconds() == 0
    original = (raw / "fetch.json").read_bytes()
    fetch_dataset(dataset, tmp_path / "cache")
    assert len(calls) == 3
    assert (raw / "fetch.json").read_bytes() == original


def test_no_audio_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr("onolys_eval.fetch.urlopen", lambda *a, **k: io.BytesIO(b"pdf"))
    raw = fetch_dataset(DatasetManifest.model_validate(manifest_data()), tmp_path)
    assert not (raw / "one/audio.mp3").exists()


def test_interrupted_download_never_becomes_existing_file(tmp_path, monkeypatch, dataset):
    class Interrupted(io.BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise URLError("interrupted")
            return super().read(2)

    monkeypatch.setattr("onolys_eval.fetch.urlopen", lambda *a, **k: Interrupted(b"broken"))
    with pytest.raises(URLError, match="interrupted"):
        fetch_dataset(dataset, tmp_path)
    assert not list((tmp_path / "synthetic/raw/one").iterdir())
    monkeypatch.setattr("onolys_eval.fetch.urlopen", lambda *a, **k: io.BytesIO(b"complete"))
    raw = fetch_dataset(dataset, tmp_path)
    assert (raw / "one/coded.pdf").read_bytes() == b"complete"


@pytest.mark.parametrize("alias", [False, True])
def test_cache_inside_unrelated_git_tree_refused(tmp_path, dataset, alias):
    repo = tmp_path / "other-repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    cache = repo / "nested/new/cache"
    if alias:
        link = tmp_path / "alias"
        link.symlink_to(repo, target_is_directory=True)
        cache = link / "new/cache"
    with pytest.raises(ValueError, match="git work tree"):
        fetch_dataset(dataset, cache)
    assert not cache.exists()


def test_linked_worktree_cache_refused(tmp_path, dataset):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c",
                    "user.email=test@example.org", "commit", "--allow-empty", "-qm", "initial"],
                   check=True)
    linked = tmp_path / "linked"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-qb", "test", str(linked)],
                   check=True)
    with pytest.raises(ValueError, match="git work tree"):
        fetch_dataset(dataset, linked / "cache")


def test_nested_session_symlink_into_git_refused(tmp_path, dataset):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    raw = tmp_path / "cache/synthetic/raw"
    raw.mkdir(parents=True)
    (raw / "one").symlink_to(repo, target_is_directory=True)
    with pytest.raises(ValueError, match="git work tree"):
        fetch_dataset(dataset, tmp_path / "cache")
    assert not (repo / "coded.pdf").exists()


def test_cli_fetch_uses_manifest_and_selected_cache(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("onolys_eval.fetch.urlopen", lambda *a, **k: io.BytesIO(b"pdf"))
    assert cli.main(["fetch", "casaa-miti421-video2013", "--cache", str(tmp_path)]) == 0
    assert len(list(tmp_path.glob("*/raw/*/coded.pdf"))) == 8
    assert "casaa-miti421-video2013" in capsys.readouterr().out


def test_default_cache_and_unknown_dataset(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_cache() == Path.home() / ".cache/onolys-eval"
    with pytest.raises(SystemExit) as error:
        cli.main(["fetch", "../escape", "--cache", str(tmp_path)])
    assert error.value.code == 2


def test_preexisting_files_are_skipped_and_recorded(tmp_path, monkeypatch, dataset):
    target = tmp_path / "synthetic/raw/one/coded.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"already here")
    calls = []

    def download(url, **kwargs):
        calls.append(url)
        return io.BytesIO(b"new")

    monkeypatch.setattr("onolys_eval.fetch.urlopen", download)
    raw = fetch_dataset(dataset, tmp_path)
    assert dataset.sessions[0].coded_url not in calls
    assert target.read_bytes() == b"already here"
    record = json.loads((raw / "fetch.json").read_text())["files"]["one/coded.pdf"]
    assert record["sha256"] == hashlib.sha256(b"already here").hexdigest()


def test_truncated_http_body_is_not_published(tmp_path, monkeypatch, dataset):
    class Truncated(io.BytesIO):
        def __init__(self, payload):
            super().__init__(payload)
            self.headers = {"Content-Length": "100"}

    monkeypatch.setattr("onolys_eval.fetch.urlopen", lambda *a, **k: Truncated(b"short"))
    with pytest.raises(OSError, match="Incomplete download"):
        fetch_dataset(dataset, tmp_path)
    assert not list((tmp_path / "synthetic/raw/one").iterdir())


def test_completed_provenance_survives_later_download_failure(tmp_path, monkeypatch, dataset):
    def download(url, **kwargs):
        if "uncoded" in url:
            raise URLError("offline")
        return io.BytesIO(b"complete")

    monkeypatch.setattr("onolys_eval.fetch.urlopen", download)
    with pytest.raises(URLError, match="offline"):
        fetch_dataset(dataset, tmp_path)
    raw = tmp_path / "synthetic/raw"
    original = json.loads((raw / "fetch.json").read_text())["files"]["one/coded.pdf"]
    monkeypatch.setattr("onolys_eval.fetch.urlopen", lambda *a, **k: io.BytesIO(b"retry"))
    fetch_dataset(dataset, tmp_path)
    assert json.loads((raw / "fetch.json").read_text())["files"]["one/coded.pdf"] == original
