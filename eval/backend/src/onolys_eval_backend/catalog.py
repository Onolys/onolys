"""Allowlisted engine choices and validated private dataset metadata."""

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from onolys_engine_core.presets import PresetInfo, list_presets
from onolys_eval.manifest import DatasetManifest, SessionManifest
from pydantic import BaseModel

router = APIRouter(prefix="/v1")
_IDENTIFIER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class EngineOption(BaseModel):
    id: str
    label: str
    engine: str
    config: str | None = None
    prod: bool = False
    version: str | None = None


class SelectionDefaults(BaseModel):
    engines: list[str]
    presets: list[str]


class ModeDefaults(BaseModel):
    dataset: SelectionDefaults
    upload: SelectionDefaults


class OptionsResponse(BaseModel):
    engines: list[EngineOption]
    presets: list[PresetInfo]
    defaults: ModeDefaults


class DatasetMetadata(BaseModel):
    dataset_id: str
    title: str
    license_note: str
    source_page: str
    miti_version: Literal["4.2.1"]
    session_count: int


class DatasetListResponse(BaseModel):
    datasets: list[DatasetMetadata]


class DatasetSession(SessionManifest):
    has_gold: bool


class DatasetDetail(DatasetManifest):
    sessions: list[DatasetSession]


def _upload(request: Request, upload_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", upload_id):
        raise HTTPException(404, "Upload not found.")
    try:
        upload = request.app.state.services.repository.get_upload(upload_id)
    except Exception:
        raise HTTPException(503, "Upload unavailable.") from None
    if upload is None:
        raise HTTPException(404, "Upload not found.")
    return upload


@router.get("/options", response_model=OptionsResponse, response_model_exclude_none=True)
def options(
    request: Request, mode: Literal["dataset", "upload"] = "dataset", upload_id: str | None = None,
) -> OptionsResponse:
    show_human = mode == "dataset"
    if mode == "upload" and upload_id is not None:
        show_human = _upload(request, upload_id).get("has_gold") is True
    config = request.app.state.config
    services = request.app.state.services
    try:
        registry = getattr(services, "registry", None) or request.app.state.catalog.registry
        engines = []
        if show_human:
            engines.append(EngineOption(id="human", label="Human score", engine="human"))
        for info in registry.engines():
            choices = (
                [(f"{info.name}:{v.id}", v.label, v.id) for v in info.variants]
                if info.variants else [(info.name, "MITI lean" if info.name == "miti"
                                       else info.name, None)]
            )
            for option_id, label, variant in choices:
                prod = option_id == config.prod_engine
                engines.append(EngineOption(
                    id=option_id, label=label + (" (prod)" if prod else ""), engine=info.name,
                    config=variant, prod=prod, version=info.version,
                ))
        presets = [p for p in list_presets(services.routes, config.default_preset)
                   if not p.name.startswith("test-")]
        # A misconfigured production default must never advertise an unselectable ID.
        if (config.prod_engine not in {e.id for e in engines}
                or config.default_preset not in {p.name for p in presets}):
            raise ValueError("Unavailable production selection")
    except Exception:
        raise HTTPException(503, "Engine options unavailable.") from None
    return OptionsResponse(engines=engines, presets=presets, defaults=ModeDefaults(
        dataset=SelectionDefaults(engines=["human", config.prod_engine],
                                  presets=[config.default_preset]),
        upload=SelectionDefaults(engines=[config.prod_engine], presets=[config.default_preset]),
    ))


def read_dataset(bucket, dataset_id: str) -> DatasetManifest:
    """Validate both SP2 metadata and its identity against the bucket directory."""
    manifest = DatasetManifest.model_validate(
        bucket.read_json(f"datasets/{dataset_id}/manifest.json")
    )
    if manifest.dataset_id != dataset_id:
        raise ValueError("Dataset identity mismatch")
    return manifest


@router.get("/datasets", response_model=DatasetListResponse)
def datasets(request: Request) -> DatasetListResponse:
    try:
        bucket = request.app.state.services.bucket
        manifests = []
        for path in sorted(bucket.list("datasets/")):
            parts = path.split("/")
            if len(parts) == 3 and parts[2] == "manifest.json":
                if not _IDENTIFIER.fullmatch(parts[1]):
                    raise ValueError("Invalid dataset identity")
                manifest = read_dataset(bucket, parts[1])
                manifests.append(DatasetMetadata(
                    **manifest.model_dump(exclude={"sessions"}),
                    session_count=len(manifest.sessions),
                ))
        return DatasetListResponse(datasets=manifests)
    except Exception:
        raise HTTPException(503, "Dataset catalog unavailable.") from None


@router.get("/datasets/{dataset_id}", response_model=DatasetDetail)
def dataset_detail(request: Request, dataset_id: str) -> DatasetDetail:
    if not _IDENTIFIER.fullmatch(dataset_id):
        raise HTTPException(404, "Dataset not found.")
    try:
        bucket = request.app.state.services.bucket
        manifest = read_dataset(bucket, dataset_id)
        objects = set(bucket.list(f"datasets/{dataset_id}/"))
        sessions = [DatasetSession(
            **session.model_dump(),
            has_gold=f"datasets/{dataset_id}/{session.session_id}/gold.json" in objects,
        ) for session in manifest.sessions]
        return DatasetDetail(**manifest.model_dump(exclude={"sessions"}), sessions=sessions)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset not found.") from None
    except Exception:
        raise HTTPException(503, "Dataset catalog unavailable.") from None
