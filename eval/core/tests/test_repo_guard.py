"""Keep dataset content out of this public repository's git index."""

import subprocess
from pathlib import Path

import pytest

MAX_FILE_BYTES = 200_000


def assert_eval_files_safe(repo: Path) -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "eval/"], cwd=repo
    ).decode().split("\0")
    violations = []
    for name in filter(None, tracked):
        path = repo / name
        if path.suffix.lower() in {".pdf", ".mp3"} or path.name.lower() in {
            "transcript.json", "gold.json"
        }:
            violations.append(f"dataset content: {name}")
        if path.stat().st_size > MAX_FILE_BYTES:
            violations.append(f"over {MAX_FILE_BYTES} bytes: {name}")
    assert not violations, "Unsafe tracked eval files:\n" + "\n".join(violations)


def test_tracked_eval_files_are_safe():
    repo = Path(__file__).resolve().parents[3]
    assert_eval_files_safe(repo)


@pytest.fixture
def synthetic_repo(tmp_path):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    return tmp_path


def track(repo, name, content):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    subprocess.run(["git", "add", "--", name], cwd=repo, check=True)


@pytest.mark.parametrize("name", ["sample.pdf", "sample.mp3", "transcript.json", "gold.json"])
def test_guard_rejects_tracked_dataset_content(synthetic_repo, name):
    track(synthetic_repo, f"eval/example/nested/{name}", b"synthetic")
    with pytest.raises(AssertionError, match="dataset content"):
        assert_eval_files_safe(synthetic_repo)


def test_guard_rejects_oversized_tracked_file(synthetic_repo):
    track(synthetic_repo, "eval/example/oversized.txt", b"x" * (MAX_FILE_BYTES + 1))
    with pytest.raises(AssertionError, match="over 200000 bytes"):
        assert_eval_files_safe(synthetic_repo)


def test_guard_allows_metadata_at_limit_and_ignores_untracked_data(synthetic_repo):
    track(synthetic_repo, "eval/example/manifest.yaml", b"x" * MAX_FILE_BYTES)
    (synthetic_repo / "eval/example/transcript.json").write_text("synthetic")
    assert_eval_files_safe(synthetic_repo)
