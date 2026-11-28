"""Allowlisted engine choices and validated private dataset metadata."""

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from onolys_engine_core.llm.models import find_model
from onolys_engine_core.llm.routes import resolve_preset
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


class TierOption(BaseModel):
    id: str
    efforts: list[str]
    default_effort: str


class ModelOption(BaseModel):
    id: str
    label: str
    context_tokens: int
    max_output_tokens: int
    tiers: list[TierOption]


class ComboSelection(BaseModel):
    models: list[str]
    tiers: list[str]
    efforts: list[str]


class SelectionDefaults(BaseModel):
    engines: list[str]
    selection: ComboSelection
    label: str


class ModeDefaults(BaseModel):
    dataset: SelectionDefaults
    upload: SelectionDefaults


class OptionsResponse(BaseModel):
    engines: list[EngineOption]
    models: list[ModelOption]
    defaults: ModeDefaults


class DatasetMetadata(BaseModel):
    dataset_id: str
    title: str
    license_note: str
    source_page: str
    miti_version: Literal["4.2.1", "4.2", "4.0"] | None
    label_scheme: str | None = None
    source_media: list[Literal["audio", "video", "transcript"]]
    transcript_origin: Literal["human", "auto_captions", "translated", "stt_ours"] | None = None
    labels_summary: str | None = None
    language: str = "en"
    overlaps_with: list[dict[str, str]] = []
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
        models = [ModelOption(
            id=m.id, label=m.label, context_tokens=m.context_tokens,
            max_output_tokens=m.max_output_tokens,
            tiers=[TierOption(id=t.id, efforts=list(t.efforts), default_effort=t.default_effort)
                   for t in m.tiers.values()],
        ) for m in services.models.values()]
        # Default combo = resolved `mid` route; never advertise an unmapped or test selection.
        if (config.prod_engine not in {e.id for e in engines}
                or config.default_preset.startswith("test-")):
            raise ValueError("Unavailable production selection")
        mid = resolve_preset(config.default_preset, services.routes)[0]["mid"]
        provider, _, tier = mid.litellm_id.partition("/")
        model = find_model(services.models, provider, tier)
        effort = mid.extra_params.get("reasoning_effort")
        if model is None or effort not in model.tiers[tier].efforts:
            raise ValueError("Unavailable production selection")
        selection = ComboSelection(models=[model.id], tiers=[tier], efforts=[effort])
        label = f"{model.label} / {tier} / {effort} (prod)"
    except Exception:
        raise HTTPException(503, "Engine options unavailable.") from None
    return OptionsResponse(engines=engines, models=models, defaults=ModeDefaults(
        dataset=SelectionDefaults(engines=["human", config.prod_engine],
                                  selection=selection, label=label),
        upload=SelectionDefaults(engines=[config.prod_engine], selection=selection, label=label),
    ))


def read_dataset(bucket, dataset_id: str) -> DatasetManifest:
    """Validate both the dataset metadata and its identity against the bucket directory."""
    manifest = DatasetManifest.model_validate(
        bucket.read_json(f"datasets/{dataset_id}/manifest.json")
    )
    if manifest.dataset_id != dataset_id:
        raise ValueError("Dataset identity mismatch")
    return manifest


@router.get("/datasets", response_model=DatasetListResponse)
def datasets(request: Request) -> DatasetListResponse:
    try:
        bucket = request.app.state.services.datasets
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
        bucket = request.app.state.services.datasets
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
