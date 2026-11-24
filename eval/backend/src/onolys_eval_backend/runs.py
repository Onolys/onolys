"""Persisted eval fanout and exactly-once terminal accounting.

Transaction callbacks contain only state calculations. Provider calls and bucket
writes happen after claiming, outside Firestore's retryable callback.
"""

import asyncio
import hashlib
import json
import os
import random
import re
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from onolys_engine_core.context import RunContext
from onolys_engine_core.engine import RunUsage
from onolys_engine_core.errors import ConfigError, InputError
from onolys_engine_core.llm.config import LLMConfig
from onolys_engine_core.llm.errors import (
    LLMBadOutput,
    LLMError,
    LLMRateLimited,
    LLMTimeout,
    LLMUnavailable,
)
from onolys_engine_core.llm.litellm_client import LiteLLMClient
from onolys_engine_core.llm.models import load_models, models_path
from onolys_engine_core.llm.routes import combo_routes, resolve_preset
from onolys_engine_core.llm.types import MetricsCollector
from onolys_engine_core.transcript_input import (
    inferred_clinician_speaker,
    validate_transcript_input,
)
from onolys_engine_core.validated_run import OutputInvalid, run_validated
from onolys_eval.adapters import miti_lean_scores, oneshot_scores
from onolys_eval.gold import Gold
from onolys_eval.metrics import Scores
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from onolys_eval_backend.catalog import _IDENTIFIER, read_dataset
from onolys_eval_backend.costs import PriceBook
from onolys_eval_backend.matrix import (
    RunTooLarge,
    SelectionError,
    combo_key,
    plan_units,
    validate_selection,
)
from onolys_eval_backend.storage import store_output
from onolys_eval_backend.uploads import validate_gold, validate_span

router = APIRouter()
TERMINAL = {"done", "failed", "cancelled"}
ZERO_USAGE = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "cost_usd": 0.0}


def now():
    return datetime.now(UTC).isoformat()


class InputRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str | None = None
    session_ids: list[str] | None = None
    upload_id: str | None = None

    @model_validator(mode="after")
    def one_source(self):
        if self.upload_id is not None:
            if (
                not re.fullmatch(r"[A-Za-z0-9_-]+", self.upload_id)
                or self.dataset_id is not None
                or self.session_ids is not None
            ):
                raise ValueError("Invalid input reference")
        elif (
            not self.dataset_id
            or not _IDENTIFIER.fullmatch(self.dataset_id)
            or not self.session_ids
            or len(set(self.session_ids)) != len(self.session_ids)
        ):
            raise ValueError("Invalid input reference")
        return self


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    models: list[str] = Field(default_factory=list)
    tiers: list[str] = Field(default_factory=list)
    efforts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique(self):
        if any(len(set(v)) != len(v) for v in (self.models, self.tiers, self.efforts)):
            raise ValueError("Invalid run selection")
        return self


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: InputRef
    engines: list[str] = Field(min_length=1)
    selection: Selection = Field(default_factory=Selection)
    repeats: StrictInt = 1
    change_goal: str | None = Field(default=None, min_length=1, max_length=4000)
    language: str | None = Field(default=None, min_length=1, max_length=64)
    coded_span: dict | None = None

    @model_validator(mode="after")
    def check_selection(self):
        if self.repeats not in (1, 3) or len(set(self.engines)) != len(self.engines):
            raise ValueError("Invalid run selection")
        if self.input.dataset_id and self.coded_span is not None:
            raise ValueError("Dataset spans come from the manifest")
        return self


class UnitTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    unit_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")


def _hash(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _inputs(services, body):
    """Read and validate everything before publishing any run or bucket object."""
    ref = body.input
    if ref.dataset_id:
        manifest = read_dataset(services.bucket, ref.dataset_id)
        sessions = {s.session_id: s for s in manifest.sessions}
        if any(sid not in sessions for sid in ref.session_ids):
            raise ValueError("Unknown dataset session")
        sources = []
        for sid in ref.session_ids:
            session = sessions[sid]
            base = f"datasets/{ref.dataset_id}/{sid}"
            sources.append(
                {
                    "session_id": sid,
                    "transcript_path": f"{base}/transcript.json",
                    "gold_path": f"{base}/gold.json",
                    "coded_span": session.coded_span.model_dump() if session.coded_span else None,
                    "change_goal": session.change_goal,
                    "provenance": session.model_dump(mode="json"),
                }
            )
    else:
        upload = services.repository.get_upload(ref.upload_id)
        if upload is None:
            raise HTTPException(404, "Upload not found.")
        if upload.get("status") != "ready":
            raise HTTPException(409, "Upload is not ready.")
        sources = [
            {
                "session_id": ref.upload_id,
                "transcript_path": upload["transcript_path"],
                "gold_path": upload.get("gold_path") if upload.get("has_gold") is True else None,
                "coded_span": body.coded_span
                if body.coded_span is not None
                else upload.get("coded_span"),
                "change_goal": body.change_goal or upload.get("change_goal"),
                "language": body.language or upload.get("language"),
                "provenance": {
                    "upload_id": ref.upload_id,
                    "kind": upload.get("kind"),
                    "stt_run": upload.get("stt_run"),
                },
            }
        ]
    return _validate_sources(services, sources, body)


def _validate_sources(services, sources, body):
    """Also accepts trusted server-saved snapshots for a later rerun endpoint."""
    ref = body.input
    expected_ids = ref.session_ids if ref.dataset_id else [ref.upload_id]
    if not sources or [source["session_id"] for source in sources] != expected_ids:
        raise ValueError("Saved input sessions do not match input reference")
    resolved = []
    for source in sources:
        transcript = validate_transcript_input(services.bucket.read_json(source["transcript_path"]))
        if source.get("transcript_sha256") and source["transcript_sha256"] != _hash(
            transcript.model_dump(mode="json")
        ):
            raise ValueError("Saved transcript integrity mismatch")
        clinician = inferred_clinician_speaker(transcript)
        clients = {t.speaker for t in transcript.turns if t.role == "client"}
        if clinician is None or not clients:
            raise ValueError("Unresolved speakers")
        validate_span(transcript, source["coded_span"])
        gold = None
        if source["gold_path"]:
            try:
                gold = Gold.model_validate(services.bucket.read_json(source["gold_path"]))
            except FileNotFoundError:
                if "human" in body.engines:
                    raise ValueError("Human requires gold") from None
            if gold is not None:
                if source.get("gold_sha256") and source["gold_sha256"] != _hash(
                    gold.model_dump(mode="json", by_alias=True)
                ):
                    raise ValueError("Saved gold integrity mismatch")
                validate_gold(gold, transcript)
                if ref.dataset_id and (
                    gold.dataset_id != ref.dataset_id or gold.session_id != source["session_id"]
                ):
                    raise ValueError("Gold identity mismatch")
        if "human" in body.engines and gold is None:
            raise ValueError("Human requires gold")
        resolved.append(
            {
                **source,
                "transcript": transcript.model_dump(mode="json"),
                "gold": gold.model_dump(mode="json", by_alias=True) if gold else None,
                "language": source.get("language") or body.language or transcript.language,
                "speaker_map": {
                    "subject": clinician,
                    **({"other": next(iter(clients))} if len(clients) == 1 else {}),
                },
            }
        )
    return resolved


def _git_sha():
    # Deploy builds inject GIT_SHA; source checkouts resolve git without a shell.
    value = os.environ.get("GIT_SHA") or os.environ.get("COMMIT_SHA")
    if value:
        return value
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL, timeout=2
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def create_run(services, config, body, created_by, *, registry=None, input_ref=None):
    """Create a run; input_ref is an optional trusted snapshot from an existing run.

    HTTP clients can only submit RunRequest.input. The rerun layer can pass the
    original run's input_ref here to preserve bytes and effective session settings.
    """
    registry = registry or services.registry
    infos = registry.engines()
    choices = {
        f"{info.name}:{v.id}" if v else info.name: info
        for info in infos
        for v in (info.variants or [None])
    }
    if any(e != "human" and e not in choices for e in body.engines):
        raise ValueError("Unknown engine")
    models = getattr(services, "models", None) or load_models(
        models_path(os.environ, config.routes_file)
    )
    engines = list(body.engines)
    if body.input.dataset_id and "human" not in engines:
        engines.append("human")
    combos, _dropped = validate_selection(
        {m.id: {t.id: list(t.efforts) for t in m.tiers.values()} for m in models.values()},
        body.selection.model_dump(),
        any(e != "human" for e in engines),
    )
    session_ids = body.input.session_ids if body.input.dataset_id else [body.input.upload_id]
    # Pure and IO-free: oversized runs are rejected before anything is read or written.
    plan = plan_units([{"session_id": sid} for sid in session_ids], engines, combos, body.repeats)
    base = config.default_preset
    resolved_combos = {
        combo_key(c): _combo_snapshot(_routes_for(services.routes, base, models, c), c)
        for c in combos
    }
    sources = (
        _validate_sources(services, input_ref["sessions"], body)
        if input_ref is not None
        else _inputs(services, body)
    )
    rid = uuid4().hex
    saved_sources, units = [], {}
    for source in sources:
        sid = source["session_id"]
        transcript, gold = source["transcript"], source["gold"]
        saved = {k: v for k, v in source.items() if k not in {"transcript", "gold"}}
        saved["source_transcript_path"] = saved["transcript_path"]
        saved["source_gold_path"] = saved["gold_path"]
        saved["transcript_path"] = f"runs/{rid}/inputs/{sid}/transcript.json"
        saved["gold_path"] = f"runs/{rid}/inputs/{sid}/gold.json" if gold else None
        saved["transcript_sha256"] = _hash(transcript)
        saved["gold_sha256"] = _hash(gold) if gold else None
        services.bucket.write_json(saved["transcript_path"], transcript)
        if gold:
            services.bucket.write_json(saved["gold_path"], gold)
        saved_sources.append(saved)
        for planned in (p for p in plan if p["session_id"] == sid):
            engine = planned["engine"]
            uid = f"u{len(units):04d}"
            span = gold["coded_span"] if engine == "human" else source["coded_span"]
            units[uid] = {
                "session_id": sid,
                "engine": engine,
                "preset": None,
                "combo": planned["combo"],
                "combo_key": planned["combo_key"],
                "repeat": planned["repeat"],
                "status": "queued",
                "stage": "queued",
                "coded_span": span,
                "warnings": ["human_span_differs"]
                if engine == "human" and span != source["coded_span"]
                else [],
            }
    run = {
        "input": body.input.model_dump(exclude_none=True),
        "input_ref": {"sessions": saved_sources},
        "engines": engines,
        "selection": body.selection.model_dump(),
        "combos": combos,
        # Legacy-shaped fields keep read_runs working until Task 6 reads combos.
        "presets": [],
        "resolved_presets": {},
        "base_preset": base,
        "repeats": body.repeats,
        "change_goal": body.change_goal,
        "language": body.language,
        "coded_span": body.coded_span,
        "status": "queued",
        "created_by": created_by,
        "created_at": now(),
        "cancel_requested": False,
        "total_units": len(units),
        "completed_units": 0,
        "done_units": 0,
        "failed_units": 0,
        "cancelled_units": 0,
        "usage": dict(ZERO_USAGE),
        "cost_usd_est": 0.0,
        "unpriced_units": 0,
        "engine_git_sha": _git_sha(),
        "engine_versions": {e: choices[e].version for e in engines if e != "human"},
        "resolved_combos": resolved_combos,
    }
    services.repository.create_run(rid, run, units)
    for uid in units:
        try:
            services.queue.enqueue("unit", {"run_id": rid, "unit_id": uid})
        except Exception:
            # Ambiguous enqueue failures may have delivered. Terminalization wins
            # only while still queued; already-claimed work owns its completion.
            finish_unit(
                services.repository,
                rid,
                uid,
                {"status": "failed", "error": {"code": "enqueue_failed"}},
                expected={"queued"},
            )
    return rid, services.repository.get_run(rid)["status"]


@router.post("/v1/runs")
def post_run(request: Request, body: RunRequest):
    services = request.app.state.services
    try:
        rid, status = create_run(
            services,
            request.app.state.config,
            body,
            request.state.admin_claims["email"].strip().lower(),
            registry=getattr(services, "registry", None) or request.app.state.catalog.registry,
        )
        return {
            "run_id": rid,
            "status": status,
            "engines": services.repository.get_run(rid)["engines"],
        }
    except HTTPException:
        raise
    except (SelectionError, RunTooLarge) as error:
        raise HTTPException(422, str(error)) from None
    except (ValueError, FileNotFoundError, InputError):
        raise HTTPException(422, "Invalid run selection or input.") from None
    except Exception:
        raise HTTPException(503, "Run creation unavailable.") from None


def finish_unit(repository, rid, uid, result, *, expected=None):
    """One transaction accounts a terminal unit and finalizes its parent once."""

    finished_at = now()

    def mutate(run, unit):
        if unit["status"] in TERMINAL or (expected and unit["status"] not in expected):
            return None
        status = result["status"]
        usage = result.get("run_info", {}).get("usage") or ZERO_USAGE
        total_usage = {
            k: run["usage"].get(k, 0) + usage.get(k, 0)
            for k in ("input_tokens", "output_tokens", "calls")
        }
        old_cost, new_cost = run["usage"].get("cost_usd"), usage.get("cost_usd")
        total_usage["cost_usd"] = (
            old_cost + new_cost if old_cost is not None and new_cost is not None else None
        )
        updates = {
            "completed_units": run["completed_units"] + 1,
            "done_units": run["done_units"] + int(status == "done"),
            "failed_units": run["failed_units"] + int(status == "failed"),
            "cancelled_units": run["cancelled_units"] + int(status == "cancelled"),
            "usage": total_usage,
            "cost_usd_est": run.get("cost_usd_est", 0) + (result.get("cost_usd_est") or 0),
            "unpriced_units": run.get("unpriced_units", 0) + int(result.get("unpriced", False)),
        }
        if updates["completed_units"] == run["total_units"]:
            done = updates["done_units"]
            updates["status"] = (
                "done" if done == run["total_units"] else "partial" if done else "failed"
            )
            updates["finished_at"] = finished_at
        return updates, {**result, "stage": result["status"], "finished_at": finished_at}

    return repository.transact_unit(rid, uid, mutate)


@router.post("/v1/runs/{run_id}/cancel")
def cancel_run(request: Request, run_id: str):
    repository = request.app.state.services.repository
    if not repository.cancel_run(run_id):
        raise HTTPException(404, "Run not found.")
    # Finalize pending units immediately, including ones never successfully queued.
    # In-flight units retain ownership and finish normally; no provider cancellation.
    for uid in repository.list_units(run_id):
        finish_unit(repository, run_id, uid, {"status": "cancelled"}, expected={"queued"})
    return {"run_id": run_id, "status": repository.get_run(run_id)["status"]}


def _metric_usage(metrics, start=0):
    records = metrics.records[start:]
    return RunUsage(
        input_tokens=sum(r["input_tokens"] for r in records),
        output_tokens=sum(r["output_tokens"] for r in records),
        calls=len(records),
        cost_usd=sum(r["cost_usd"] for r in records)
        if all(r["cost_usd"] is not None for r in records)
        else None,
    )


def _add_usage(a, b):
    if a is None:
        return b
    cost = a.cost_usd + b.cost_usd if a.cost_usd is not None and b.cost_usd is not None else None
    return RunUsage(
        input_tokens=a.input_tokens + b.input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
        calls=a.calls + b.calls,
        cost_usd=cost,
    )


UNIT_BUDGET_S = 840
MAX_ATTEMPTS = 3
RETRY_DELAYS_S = (5, 20)
MIN_RETRY_BUDGET_S = 120
_PERMANENT_STATUS = {400, 401, 403, 404, 422}
_PERMANENT_ERROR_TYPES = {"auth", "authentication", "bad_request", "not_found", "invalid_request"}


def _llm_cause(exc):
    """First LLMError on the `__cause__`/`__context__` chain (miti wraps it in AllRunsFailed)."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, LLMError):
            return exc
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return None


def _llm_transient(err):
    """SHIM: replace with SP03's `onolys_engine_core.llm.errors.is_transient` once it lands.

    Reads SP02's `http_status`/`error_type` via getattr so it works before and after SP02.
    """
    if isinstance(err, LLMBadOutput) or not isinstance(err, LLMUnavailable | LLMTimeout):
        return False
    if getattr(err, "no_retry", False):
        return False
    status = getattr(err, "http_status", None) or getattr(err, "status_code", None)
    if status in _PERMANENT_STATUS or getattr(err, "error_type", None) in _PERMANENT_ERROR_TYPES:
        return False
    return True


def is_retryable(exc):
    if any(isinstance(e, _PERMANENT) for e in _chain(exc)):
        return False
    cause = _llm_cause(exc)
    return cause is not None and _llm_transient(cause)


def _chain(exc):
    seen = set()
    while exc is not None and id(exc) not in seen:
        yield exc
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__


def _llm_code(err):
    if isinstance(err, LLMRateLimited):
        return "llm_rate_limited"
    if isinstance(err, LLMTimeout):
        return "llm_timeout"
    return "llm_unavailable"


def _estimate_cost(services, run, unit, usage, metrics):
    prices = getattr(services, "prices", None) or PriceBook.from_yaml()
    if usage.cost_usd is not None:
        return usage.cost_usd, False
    # Metrics records are the only sound way to price mixed-model engines.
    if metrics.records:
        estimates = [prices.estimate(record, record["model"]) for record in metrics.records]
        unknown = any(e.cost_usd is None for e in estimates)
        return sum(e.cost_usd or 0 for e in estimates), unknown
    if unit.get("combo_key"):
        snap = run["resolved_combos"].get(unit["combo_key"])
        models = {snap["litellm_id"]} if snap else set()
    else:
        models = set(run["resolved_presets"].get(unit["preset"], {}).values())
    estimate = prices.estimate(usage, next(iter(models)) if len(models) == 1 else "")
    return estimate.cost_usd, estimate.cost_usd is None


def _cost(services, run, unit, usage, metrics):
    # Missing/broken price metadata must never prevent terminal unit accounting.
    try:
        return _estimate_cost(services, run, unit, usage, metrics)
    except Exception:
        return usage.cost_usd, usage.cost_usd is None


def _routes_for(registry, base_preset, models, combo):
    """Route set for one combo: the base preset's routes re-pointed at the combo (PRD R6)."""
    model = next(m for m in models.values() if m.id == combo["model"])
    base = resolve_preset(base_preset, registry)[0]
    return combo_routes(base, model, combo["tier"], combo["effort"])


def _combo_snapshot(routes, combo):
    route = next(iter(routes.values()))
    return {
        "litellm_id": route.litellm_id,
        "effort": combo["effort"],
        "max_output_tokens": route.max_output_tokens,
        "context_tokens": route.context_tokens,
        "supports_temperature": route.supports_temperature,
        "caching_mode": route.caching_mode,
    }


class _ExecutionConfigChanged(Exception):
    """Queued AI work no longer matches its saved execution provenance."""


_PERMANENT = (OutputInvalid, InputError, ConfigError, _ExecutionConfigChanged)


async def execute_unit(services, rid, uid):
    repository = services.repository
    # Read immutable execution inputs before claiming: transient read failures must
    # leave queued work retryable. The transaction still checks live ownership/cancel.
    run, unit = repository.get_run(rid), repository.get_unit(rid, uid)
    started_at = now()

    def claim(run, unit):
        if unit["status"] != "queued" or run.get("cancel_requested"):
            return None
        return {"status": "running"}, {
            "status": "running",
            "stage": "coding",
            "started_at": started_at,
        }

    if not repository.transact_unit(rid, uid, claim):
        # A cancel may race dispatch before its sweep reaches this unit.
        run = repository.get_run(rid)
        if run and run.get("cancel_requested"):
            finish_unit(repository, rid, uid, {"status": "cancelled"}, expected={"queued"})
        return
    metrics = MetricsCollector()
    usage = None
    attempts = 0
    carried = None
    try:
        source = next(
            s for s in run["input_ref"]["sessions"] if s["session_id"] == unit["session_id"]
        )
        if unit["engine"] == "human":
            output = services.bucket.read_json(source["gold_path"])
            gold = Gold.model_validate(output)
            scores = Scores(counts=gold.counts, globals=gold.globals)
            run_info = {"usage": dict(ZERO_USAGE)}
            cost, unpriced = 0.0, False
        else:
            transcript = validate_transcript_input(
                services.bucket.read_json(source["transcript_path"])
            )
            engine = services.engine(unit["engine"])
            if unit.get("combo"):
                # Combo unit: rebuild routes from the live models.yaml and compare to the
                # snapshot taken at creation (drift guard).
                routes = _routes_for(
                    services.routes, run["base_preset"], services.models, unit["combo"]
                )
                config_changed = run["resolved_combos"].get(unit["combo_key"]) != _combo_snapshot(
                    routes, unit["combo"]
                )
            else:
                # Legacy preset unit, kept until stored legacy runs drain.
                routes, _ = resolve_preset(unit["preset"], services.routes)
                config_changed = run["resolved_presets"].get(unit["preset"]) != {
                    name: route.litellm_id for name, route in routes.items()
                }
            if (
                run["engine_git_sha"] != _git_sha()
                or run["engine_versions"].get(unit["engine"]) != engine.version
                or config_changed
            ):
                raise _ExecutionConfigChanged
            params = {
                "preset": unit["preset"],
                "coded_span": unit["coded_span"],
                "speaker_map": source["speaker_map"],
                "language": source["language"],
                "change_goal": source["change_goal"],
            }
            if ":" in unit["engine"]:
                params["config"] = unit["engine"].split(":", 1)[1]

            def progress(stage, status):
                repository.update_unit(rid, uid, {"stage": str(stage)})

            factory = getattr(services, "llm_factory", None)
            sleep = getattr(services, "sleep", None) or asyncio.sleep
            budget_end = monotonic() + UNIT_BUDGET_S
            while True:
                attempts += 1
                first_record = len(metrics.records)
                llm = (
                    factory(routes, metrics) if factory else LiteLLMClient(LLMConfig(routes=routes))
                )
                ctx = RunContext(
                    llm=llm, metrics=metrics, request_id=f"{rid}-{uid}", deadline=budget_end
                )
                try:
                    async with asyncio.timeout(max(budget_end - monotonic(), 0)):
                        result = await run_validated(
                            engine, ctx, transcript, params, progress_cb=progress
                        )
                    break
                except Exception as exc:
                    remaining = budget_end - monotonic()
                    if (
                        attempts >= MAX_ATTEMPTS
                        or remaining < MIN_RETRY_BUDGET_S
                        or not is_retryable(exc)
                    ):
                        raise
                    # Failed attempt's spend is carried into the single finish_unit.
                    carried = _add_usage(
                        carried,
                        (exc.usage if isinstance(exc, OutputInvalid) else None)
                        or _metric_usage(metrics, first_record),
                    )
                    await sleep(RETRY_DELAYS_S[attempts - 1] * random.uniform(0.5, 1.0))
            output = result.output
            scores = (
                oneshot_scores(output)
                if unit["engine"].startswith("oneshot:")
                else miti_lean_scores(output)
            )
            run_info = result.run_info.model_dump(mode="json")
            usage = (
                _add_usage(carried, result.run_info.usage)
                if result.run_info.usage
                else _metric_usage(metrics)
            )
            run_info["usage"] = usage.model_dump(mode="json")
            cost, unpriced = _cost(services, run, unit, usage, metrics)
        saved = {
            **store_output(services.bucket, rid, uid, output),
            "status": "done",
            "attempts": attempts,
            "scores": scores.model_dump(mode="json"),
            "run_info": run_info,
            "cost_usd_est": cost,
            "unpriced": unpriced,
        }
    except Exception as exc:
        usage = (
            _add_usage(carried, exc.usage)
            if isinstance(exc, OutputInvalid) and exc.usage
            else usage or _metric_usage(metrics)
        )
        cost, unpriced = _cost(services, run, unit, usage, metrics)
        error_code = "engine_failed"
        retryable = is_retryable(exc)
        if isinstance(exc, OutputInvalid):
            error_code = "output_invalid"
        elif retryable:
            error_code = _llm_code(_llm_cause(exc))
        elif isinstance(exc, _ExecutionConfigChanged):
            error_code = "execution_config_changed"
        saved = {
            "status": "failed",
            "attempts": attempts,
            "error": {"code": error_code, "retryable": retryable},
            "run_info": {"usage": usage.model_dump(mode="json")},
            "cost_usd_est": cost,
            "unpriced": unpriced,
        }
    finish_unit(repository, rid, uid, saved, expected={"running"})


@router.post("/internal/tasks/unit")
async def unit_task(request: Request, body: UnitTask):
    await execute_unit(request.app.state.services, body.run_id, body.unit_id)
    return {"status": "ok"}
