"""Deterministic MITI audit; installed workspace packages only, no client or model calls.

Counts are rules applied to expected.yaml's hand-authored utterances, not predictions.
Rendered words count cache prefixes + system + user once per initial code/globals call,
including repeated prefixes across batches. No tips, schema, retries, token/cost estimates.
"""

import argparse
import hashlib
import json
from pathlib import Path

import yaml
from onolys_engine_core.llm import LLMRequest
from onolys_engine_core.llm.fixture_client import FixtureClient
from onolys_engine_core.transcript import Transcript

from onolys_miti import code_pass, globals_pass, miti
from onolys_miti.coverage import coverage as word_coverage
from onolys_miti.prepare import prepare
from onolys_miti.result import Instance
from onolys_miti.score import apply_rules, compute_summaries, count_instances

FIX = miti.DATA_DIR / "fixtures"


def render_requests(prepared, params, language=None):
    """Pure reconstruction of initial production requests (no retries/client).

    Code uses production shared parts and batch renderer; globals uses its request builder.
    call tags, unit and response models match the first run (r0) of the production passes.
    """
    parts = code_pass.build_requests_parts(params, language)
    size = parts.volleys_per_call
    if size <= 0:
        raise ValueError("volleys_per_call must be positive")
    requests = []
    for n, start in enumerate(range(0, len(prepared.volleys), size), 1):
        batch = prepared.volleys[start : start + size]
        requests.append(
            LLMRequest(
                tier=code_pass.ROUTE,
                system=parts.system,
                user=code_pass._render_batch(batch),
                response_model=parts.response_model,
                call_tag=f"{code_pass.ROUTE}:r0:b{n}",
                cache_prefixes=list(parts.cache_prefixes),
                unit=f"{batch[0].id}-{batch[-1].id}",
                max_tokens=parts.max_tokens,
            )
        )
    items = globals_pass.global_items()
    if items:
        model = globals_pass.make_response_model([i["id"] for i in items])
        requests.append(globals_pass._build_request(prepared, params, language, 0, "g", model))
    return requests


def load_fixture(spec, fixture_dir=FIX):
    transcript = Transcript.model_validate(
        json.loads((fixture_dir / spec["transcript"]).read_text())
    )
    params = json.loads((fixture_dir / spec["params"]).read_text())
    params.setdefault("change_goal", spec.get("change_goal"))
    return transcript, params, prepare(transcript, params)


def hand_instances(prepared, utterances):
    """Locate exact supplied text; invalid hand evidence is an error, never manufactured."""
    by_turn = {t.id: (v.id, t) for v in prepared.volleys for t in v.turns}
    cursors = {}
    out = []
    for n, u in enumerate(utterances, 1):
        vid, turn = by_turn[u["turn_id"]]
        start = turn.text.find(u["quote"], cursors.get(turn.id, 0))
        if start < 0 or not u["quote"]:
            raise ValueError(f"hand utterance {n} does not locate in {turn.id}")
        end = start + len(u["quote"])
        cursors[turn.id] = end
        coded = u["code"] is not None
        out.append(
            Instance(
                id=f"i{n}",
                volley_id=vid,
                turn_id=turn.id,
                start=start,
                end=end,
                start_ms=turn.start_ms,
                end_ms=turn.end_ms,
                quote=turn.text[start:end],
                code=u["code"],
                counted=coded,
                uncounted_reason=None if coded else "uncoded",
                rationale=u.get("rationale", "Hand-authored fixture"),
            )
        )
    return out


def coverage(prepared, instances):
    """Whitespace-word residual over union of located spans, including uncoded/down-counted.

    A word is covered if any non-whitespace character overlaps a located span. This is an
    offline proxy over hand utterances, not a calibrated quality gate or model coverage.
    """
    return word_coverage(prepared.volleys, instances)


def build_audit(fixture_dir=FIX):
    raw = (fixture_dir / "expected.yaml").read_bytes()
    expected = yaml.safe_load(raw)
    rows = []
    for name, spec in expected["fixtures"].items():
        transcript, params, prepared = load_fixture(spec, fixture_dir)
        requests = render_requests(prepared, params, transcript.language)
        source = hand_instances(prepared, spec["utterances"]) if "utterances" in spec else None
        final, warnings = apply_rules(source or [], miti.MITI.data.get("rules", []))
        counts = count_instances(final, code_pass.count_codes()) if source is not None else None
        words = {
            stage: sum(
                len(text.split())
                for req in requests
                if req.tier == f"miti_{stage}"
                for text in [*req.cache_prefixes, req.system, req.user]
            )
            for stage in ("code", "globals")
        }
        words["total"] = sum(words.values())
        doubles = (
            [
                v.id
                for v in prepared.volleys
                if {i.code for i in final if i.counted and i.volley_id == v.id}
                >= {"persuade", "persuade_permission"}
            ]
            if source is not None
            else None
        )
        hand_globals = {k: g["score"] for k, g in spec.get("globals", {}).items()}
        summaries = compute_summaries(
            miti.MITI.data.get("summaries", []), counts or {}, hand_globals
        )
        targets = spec.get("counts", {})
        rows.append(
            {
                "fixture": name,
                "volley_count": len(prepared.volleys),
                "volley_turn_ids": [[t.id for t in v.turns] for v in prepared.volleys],
                "batch_limit": code_pass.build_requests_parts(params).volleys_per_call,
                "batch_count": sum(r.tier == code_pass.ROUTE for r in requests),
                "request_words": words,
                "request_keys": [FixtureClient.key_for(r) for r in requests],
                "counts": counts,
                "target_counts": targets,
                "count_drift": {k: counts[k] - v for k, v in targets.items()}
                if counts is not None
                else None,
                "summaries_with_hand_globals": {k: s.value for k, s in summaries.items()},
                "target_summaries": spec.get("summaries", {}),
                "summary_drift": {
                    k: (None if summaries[k].value is None or v is None else summaries[k].value - v)
                    for k, v in spec.get("summaries", {}).items()
                },
                "persuasion_double_count_volleys": doubles,
                "persuasion_double_count": len(doubles) if doubles is not None else None,
                "coverage": coverage(prepared, source) if source is not None else None,
                "warnings": [
                    w.model_dump(exclude_none=True) for w in [*prepared.warnings, *warnings]
                ],
            }
        )
    return {
        "schema": 1,
        "pack_hash": miti.MITI.hash,
        "expected_sha256": hashlib.sha256(raw).hexdigest(),
        "source_sha256": {
            name: hashlib.sha256((miti.PKG_DIR / name).read_bytes()).hexdigest()
            for name in ("prepare.py", "score.py", "code_pass.py", "globals_pass.py", "coverage.py")
        },
        "stages": ["code", "globals"],
        "request_words_method": "Whitespace words in cache prefixes + system + user per initial "
        "call; repeated prefixes included per batch. Excludes schemas, tips and retries.",
        "coverage_method": "Whitespace words overlapping the union of located hand-authored "
        "utterance spans, including uncoded and down-counted; null when utterances undefined.",
        "limits": "Synthetic hand-authored fixtures; deterministic manual alignment evidence, "
        "not accuracy. No model outputs, network calls, latency, tokens or cost measured. "
        "Summary globals are hand targets, not evaluated global ratings.",
        "fixtures": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="JSON artifact; stdout if omitted")
    args = parser.parse_args()
    text = json.dumps(build_audit(), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
