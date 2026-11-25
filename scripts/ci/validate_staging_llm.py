#!/usr/bin/env python3
"""Validate app repository LLM vars with the selected runtime loader before deployment.

Run with `uv run --frozen --package onolys-engine-core python scripts/ci/validate_staging_llm.py`.
Only these three vars are CI inputs. Staging uses checked-out config; production runs
the trusted validator inside the promoted image against its own config/runtime.
"""
import argparse
import os
import sys
from pathlib import Path

from onolys_engine_core.errors import ConfigError
from onolys_engine_core.llm import routes

ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', choices=('staging', 'prod'), default='staging')
    parser.add_argument('--config-root', type=Path, default=ROOT / 'config')
    parser.add_argument('--stdout', action='store_true', help='emit only validated GitHub output fields')
    args = parser.parse_args()
    values = {key: os.environ.get(f"LLM_{key.upper()}", "") for key in ("provider", "model", "effort")}
    try:
        for key, value in values.items():
            if value and getattr(routes, f'{key.upper()}_ENV', None) != f'LLM_{key.upper()}':
                raise ConfigError(f'This image does not support LLM_{key.upper()}; clear overrides for rollback')
        routes.load_registry(
            args.config_root / args.environment / 'routes.yaml',
            env={f"LLM_{key.upper()}": value for key, value in values.items()},
        )
    except ConfigError as exc:
        print(f"Invalid {args.environment} LLM configuration: {exc}", file=sys.stderr)
        return 1
    # The runtime validator accepts only exact lowercase tokens from model capabilities.
    # Emit nothing until the complete set validates, so no partial values can be deployed.
    fields = ''.join(f'{key}={value}\n' for key, value in values.items())
    if args.stdout:
        print(fields, end='')
    elif output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(fields)
    print(f"{args.environment.title()} LLM configuration validated", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
