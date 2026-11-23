"""Command entry points; dataset operations are added by subsequent tasks."""

import argparse
from collections.abc import Sequence


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
        if name == "run":
            command.add_argument("session_id", help="Session identifier")
    args = parser.parse_args(argv)
    parser.error(f"{args.command} is not implemented yet")
    return 2
