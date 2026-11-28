"""Locate a config next to ROUTES_FILE, falling back to a packaged resource."""

import os
from importlib import resources
from pathlib import Path


def locate_config_file(
    name: str,
    default_resource: str,
    package: str,
) -> Path:
    """`name` next to the file named by env ROUTES_FILE if present, else the packaged default."""
    routes = os.environ.get("ROUTES_FILE")
    if routes:
        candidate = Path(routes).parent / name
        if candidate.is_file():
            return candidate
    return Path(str(resources.files(package).joinpath(default_resource)))
