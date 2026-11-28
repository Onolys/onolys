"""Re-key synthetic code/globals stubs offline using the real request renderers.

No model/client invocation. --responses supplies {call_tag: response} after hand edits
when volleys merge or batches change. All response shapes and code quotes are checked
before writing. Unchanged bytes are never rewritten. Historical adapter parity data
is deliberately outside this tool's scope (see offline-tools.md in measurements).
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Script entry point works from any cwd with the workspace packages installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from onolys_engine.llm.fixture_client import FixtureClient  # noqa: E402

from audit_report import FIX, load_fixture, render_requests  # noqa: E402
from onolys_miti import miti  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLD = FIX / "golden" / "good_practice"
GOLDEN_TEST = ROOT / "tests" / "test_golden.py"
DATA_TEST = ROOT / "tests" / "test_data.py"
PACK_TEST = ROOT / "tests" / "test_miti_pack.py"
REPORT = FIX / "evaluation" / "report_no_rating.json"


def golden_requests():
    # The golden run uses n_runs=1 and this params fixture's goal/map; n_runs is not rendered.
    spec = {"transcript": "good_practice.json", "params": "good_practice.params.json"}
    transcript, params, prepared = load_fixture(spec)
    return render_requests(prepared, params, transcript.language)


def _validate(req, response):
    req.response_model.model_validate(response)
    if req.tier != "miti_code":
        return
    batch = {v["volley_id"]: v for v in json.loads(req.user)["volleys"]}
    ids = [v["volley_id"] for v in response["volleys"]]
    if sorted(ids) != sorted(batch):
        raise ValueError(
            f"{req.call_tag}: volley ids changed; provide --responses with hand-edited stubs"
        )
    for volley in response["volleys"]:
        turns = batch[volley["volley_id"]]["clinician_turns"]
        for u in volley["utterances"]:
            if not u["quote"] or not any(u["quote"] in t["text"] for t in turns):
                raise ValueError(f"{req.call_tag}: quote does not locate inside its volley")


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def regenerate(*, responses=None):
    """Plan and validate everything, then write only changed files; return changed paths."""
    requests = golden_requests()
    overrides = json.loads(responses.read_text()) if responses else {}
    tags = {r.call_tag for r in requests}
    if set(overrides) - tags:
        raise ValueError(f"unknown response call tags: {sorted(set(overrides) - tags)}")
    old = {p: json.loads(p.read_text()) for p in GOLD.glob("*.json")}
    code = sorted(
        [(p, v) for p, v in old.items() if "volleys" in v],
        key=lambda pair: min(int(v["volley_id"].removeprefix("v")) for v in pair[1]["volleys"]),
    )
    globals_ = [(p, v) for p, v in old.items() if "globals" in v]
    planned = {}
    keep = set()
    code_index = 0
    for req in requests:
        target = GOLD / f"{FixtureClient.key_for(req)}.json"
        if req.call_tag in overrides:
            response = overrides[req.call_tag]
        elif target in old:
            response = old[target]
        else:
            candidates = code if req.tier == "miti_code" else globals_
            index = code_index if req.tier == "miti_code" else 0
            if index >= len(candidates):
                raise ValueError(
                    f"{req.call_tag}: new batch requires --responses hand-authored stub"
                )
            response = candidates[index][1]
        _validate(req, response)
        # Preserve original bytes when re-keying an unchanged payload, including its formatting.
        original = next((p for p, payload in old.items() if payload == response), None)
        planned[target] = original.read_bytes() if original else _json(response)
        keep.add(target)
        if req.tier == "miti_code":
            code_index += 1
    keys = sorted(p.stem for p in keep)
    test = GOLDEN_TEST.read_text()
    replacement = "    expected = {\n" + "".join(f'        "{k}",\n' for k in keys) + "    }"
    test, n = re.subn(r'    expected = \{\n(?:        "[0-9a-f]{64}",\n)+    \}', replacement, test)
    if n != 1:
        raise ValueError("cannot find unique expected hash set in test_golden.py")
    planned[GOLDEN_TEST] = test.encode()
    for pin_test in (DATA_TEST, PACK_TEST):
        pinned, n = re.subn(
            r'KNOWN_PACK_HASH = "[0-9a-f]+"',
            f'KNOWN_PACK_HASH = "{miti.MITI.hash}"',
            pin_test.read_text(),
        )
        if n != 1:
            raise ValueError(f"cannot find pack hash pin in {pin_test.name}")
        planned[pin_test] = pinned.encode()
    # Only pack metadata is repinned here; behavior changes need deliberate report rebaselining.
    report = json.loads(REPORT.read_text())
    old_hash = report["header"]["protocol"]["pack_hash"]
    if old_hash != miti.MITI.hash:
        # Preserve formatting and update the same pack fingerprint in provenance too.
        planned[REPORT] = REPORT.read_bytes().replace(old_hash.encode(), miti.MITI.hash.encode())
    changed = []
    for path, content in planned.items():
        if not path.exists() or path.read_bytes() != content:
            path.write_bytes(content)
            changed.append(path)
    for path in old.keys() - keep:
        path.unlink()
        changed.append(path)
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--responses",
        type=Path,
        help="JSON object keyed by call_tag with manually edited response payloads",
    )
    args = parser.parse_args()
    changed = regenerate(responses=args.responses)
    print("\n".join(str(p) for p in changed) if changed else "No changes.")


if __name__ == "__main__":
    main()
