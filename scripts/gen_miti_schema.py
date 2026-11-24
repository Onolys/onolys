#!/usr/bin/env python3
"""Generate the one-call scoring subset from repository data, without MITI imports.

The full report contains software-derived provenance and statistics. A single run
instead authors integer counts, four integer ratings and the prose part of tips.
"""

import argparse
import json
from copy import deepcopy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "engines/miti/src/onolys_miti/data"
OUTPUT = ROOT / "engines/oneshot/src/onolys_oneshot/configs/miti/schema.json"


def _object(properties: dict) -> dict:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def generate_schema(report_path: Path = DATA / "report.schema.json",
                    pack_path: Path = DATA / "pack.yaml") -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    pack = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    definitions = report["$defs"]
    # The report's per-run count values are numeric; one call always yields integers.
    count = deepcopy(definitions["RunStats"]["properties"]["values"]["items"])
    if count["type"] != "number":
        raise ValueError("Report per-run count contract changed")
    count.update(type="integer", minimum=0)
    score = next(deepcopy(option) for option in
                 definitions["OnolysGlobal"]["properties"]["score"]["anyOf"]
                 if option.get("type") != "null")
    tips = definitions["Tip"]
    # Quote validation and optional report idea titles belong to lean; keep the
    # recorded one-shot baseline contract stable when report presentation evolves.
    tip_fields = {key: deepcopy(value) for key, value in tips["properties"].items()
                  if key not in {"quote", "title"}}
    tip_fields["item_id"]["enum"] = [item["id"] for item in pack["items"]]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:onolys:oneshot:miti:1",
        **_object({
            "counts": _object({item["id"]: deepcopy(count) for item in pack["items"]
                               if item["kind"] == "count"}),
            "globals": _object({item["id"]: {**score, "minimum": item["scale"]["min"],
                                             "maximum": item["scale"]["max"]}
                                for item in pack["items"] if item["kind"] == "global"}),
            "tips": {"type": "array", "items": _object(tip_fields)},
        }),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed schema drifts")
    args = parser.parse_args()
    rendered = json.dumps(generate_schema(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != rendered:
            parser.exit(1, "MITI one-shot schema drift; run scripts/gen_miti_schema.py\n")
    else:
        OUTPUT.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
