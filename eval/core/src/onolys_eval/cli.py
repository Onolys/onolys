"""Dataset preparation and session comparison command entry points."""

import argparse
import asyncio
import re
from collections.abc import Sequence
from pathlib import Path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="onolys-eval", description="Evaluate MITI 4.2.1 session coding."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, description in (
        ("fetch", "Download a reference dataset to the local cache."),
        ("convert", "Convert reference PDFs into transcript and gold JSON."),
        ("upload", "Upload a converted dataset to the private bucket."),
        ("run", "Compare MITI session coding with reference gold."),
    ):
        command = commands.add_parser(name, help=description, description=description)
        command.add_argument("dataset", help="Dataset identifier")
        if name in {"fetch", "convert", "upload"}:
            command.add_argument("--cache", type=Path, help="Cache directory (outside git)")
        if name == "convert":
            command.add_argument("--session", help="Convert only this session")
            command.add_argument("--dump", action="store_true", help="Print the parsed table")
            command.add_argument("--allow-warnings", action="store_true")
        if name == "run":
            command.add_argument("session_id", help="Session identifier")
            command.add_argument("--preset", help="Engine route preset")
            command.add_argument("--runs", type=int, default=1, help="Number of engine runs (default: 1)")
            command.add_argument("--source", choices=("cache", "bucket"), default="cache")
            command.add_argument("--json-out", type=Path, help="Comparison JSON path (outside git)")
    args = parser.parse_args(argv)
    if args.command == "run":
        from .manifest import load_manifest
        from .run import run_session

        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.dataset) is None:
            parser.error("Invalid dataset identifier")
        if args.runs < 1:
            parser.error("runs must be at least 1")
        manifest_path = Path(__file__).resolve().parents[3] / "datasets" / args.dataset / "manifest.yaml"
        try:
            asyncio.run(run_session(load_manifest(manifest_path), args.session_id,
                                    preset=args.preset, n_runs=args.runs,
                                    source=args.source, json_out=args.json_out))
        except (OSError, ValueError) as error:
            parser.error(str(error))
        return 0
    if args.command == "upload":
        from .manifest import load_manifest
        from .upload import upload_dataset

        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.dataset) is None:
            parser.error("Invalid dataset identifier")
        manifest_path = Path(__file__).resolve().parents[3] / "datasets" / args.dataset / "manifest.yaml"
        try:
            count = upload_dataset(load_manifest(manifest_path), args.cache)
        except (OSError, ValueError) as error:
            parser.error(str(error))
        print(f"{args.dataset}: uploaded {count} objects to the private staging bucket")
        return 0
    if args.command == "convert":
        from .convert import convert_dataset

        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.dataset) is None:
            parser.error("Invalid dataset identifier")
        try:
            return convert_dataset(args.dataset, args.cache, args.session,
                                   dump=args.dump, allow_warnings=args.allow_warnings)
        except (OSError, ValueError, KeyError) as error:
            parser.error(str(error))
    if args.command == "fetch":
        from .fetch import fetch_dataset
        from .manifest import load_manifest

        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.dataset) is None:
            parser.error("Invalid dataset identifier")
        manifest_path = Path(__file__).resolve().parents[3] / "datasets" / args.dataset / "manifest.yaml"
        try:
            raw = fetch_dataset(load_manifest(manifest_path), args.cache)
        except (OSError, ValueError) as error:
            parser.error(str(error))
        print(f"{args.dataset}: reference assets cached in {raw}")
        return 0
    parser.error(f"{args.command} is not implemented yet")
    return 2
