"""Download reference assets to an external cache, publishing only complete files.

``raw/fetch.json`` stores provenance by relative filename in ``files``. Each record
contains the source URL, SHA-256, and UTC retrieval time. Files already present are
left untouched; pre-existing files without records use their modification time.
"""

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from .manifest import DatasetManifest


def default_cache() -> Path:
    return Path.home() / ".cache/onolys-eval"


def require_external_path(path: Path) -> Path:
    """Reject paths in any worktree, resolving even non-existing symlink children."""
    resolved = path.expanduser().resolve()
    existing = resolved
    while not existing.is_dir():
        existing = existing.parent
    # Caller git environment must not hide the repository at the destination.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    result = subprocess.run(
        ["git", "-C", str(existing), "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True, check=False, env=env,
    )
    if result.returncode == 0 and result.stdout.strip() == "true":
        raise ValueError(f"Cache path is inside a git work tree: {resolved}")
    return resolved


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _download(url: str, destination: Path) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.", suffix=".part", delete=False,
        ) as output:
            temporary = Path(output.name)
            with urlopen(url, timeout=60) as response:
                headers = getattr(response, "headers", {})
                expected_length = headers.get("Content-Length")
                length = 0
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    length += len(chunk)
                if expected_length is not None and length != int(expected_length):
                    raise OSError(f"Incomplete download: {url}")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_metadata(path: Path, metadata: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, prefix=".fetch.", suffix=".part", delete=False,
        ) as output:
            temporary = Path(output.name)
            json.dump(metadata, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def fetch_dataset(manifest: DatasetManifest, cache: str | Path | None = None) -> Path:
    """Fetch manifest assets, returning the raw directory; preserve completed work."""
    cache_path = require_external_path(Path(cache) if cache is not None else default_cache())
    raw = cache_path / manifest.dataset_id / "raw"
    metadata_path = raw / "fetch.json"
    assets = []
    for session in manifest.sessions:
        for filename, url in (
            ("coded.pdf", session.coded_url),
            ("uncoded.pdf", session.uncoded_url),
            ("audio.mp3", session.audio_url),
        ):
            if url is not None:
                target = raw / session.session_id / filename
                require_external_path(target)
                assets.append((target, url))
    require_external_path(metadata_path)
    raw.mkdir(parents=True, exist_ok=True)
    metadata = (
        json.loads(metadata_path.read_text()) if metadata_path.exists()
        else {"dataset_id": manifest.dataset_id, "files": {}}
    )
    for target, url in assets:
        relative = target.relative_to(raw).as_posix()
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            _download(url, target)
            retrieved_at = datetime.now(UTC).isoformat()
        else:
            retrieved_at = metadata["files"].get(relative, {}).get("retrieved_at")
            if retrieved_at is None:
                retrieved_at = datetime.fromtimestamp(target.stat().st_mtime, UTC).isoformat()
        metadata["files"][relative] = {
            "url": url, "sha256": _sha256(target), "retrieved_at": retrieved_at,
        }
        # Persist each completed asset so an interrupted batch retains provenance.
        _write_metadata(metadata_path, metadata)
    return raw
