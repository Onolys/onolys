"""Publish converted reference datasets to the private staging bucket via ADC."""
import json
from pathlib import Path

from .fetch import default_cache, require_external_path
from .gold import load_gold
from .manifest import DatasetManifest

BUCKET = "onolys-eval-data-staging"


def upload_dataset(
    manifest: DatasetManifest, cache: str | Path | None = None, *, client=None,
) -> int:
    """Preflight every session before writing; publish the listing manifest last.

    Only manifest-listed assets are uploaded, never arbitrary files from the cache.
    A supplied storage client is useful for callers with an existing ADC client.
    """
    cache_path = require_external_path(Path(cache) if cache is not None else default_cache())
    dataset_path = cache_path / manifest.dataset_id
    prefix = f"datasets/{manifest.dataset_id}/"
    assets = []
    for session in manifest.sessions:
        session_path = dataset_path / session.session_id
        gold_path = require_external_path(session_path / "gold.json")
        gold = load_gold(gold_path)
        if (gold.dataset_id, gold.session_id) != (manifest.dataset_id, session.session_id):
            raise ValueError(f"Gold identity mismatch: {session.session_id}")
        if gold.parse.warnings:
            raise ValueError(f"Unresolved conversion warnings: {session.session_id}; run convert first")
        for filename, content_type in (
            ("transcript.json", "application/json"), ("gold.json", "application/json"),
            ("raw/coded.pdf", "application/pdf"), ("raw/uncoded.pdf", "application/pdf"),
            *([("raw/audio.mp3", "audio/mpeg")] if session.audio_url else []),
        ):
            path = (
                dataset_path / "raw" / session.session_id / Path(filename).name
                if filename.startswith("raw/") else session_path / filename
            )
            path = require_external_path(path)
            if not path.is_file():
                raise ValueError(f"Missing converted/reference asset: {path}; run fetch and convert first")
            assets.append((prefix + session.session_id + "/" + filename, path, content_type))
    if client is None:
        from google.cloud import storage

        client = storage.Client(project="onolys")
    bucket = client.bucket(BUCKET)
    for name, path, content_type in assets:
        bucket.blob(name).upload_from_filename(str(path), content_type=content_type)
    bucket.blob(prefix + "manifest.json").upload_from_string(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
        content_type="application/json",
    )
    return len(assets) + 1
