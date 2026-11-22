"""The MITI 4.2.1 definition: `MITI`, a frozen constant loaded once from `data/` and `rules.py`.

Validated by unit tests (tests/test_miti_pack.py, tests/test_data.py), not at run time.
Passes read `miti.MITI` at call time, so a test can swap the whole definition."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from onolys_miti.run_info import PackFacts, hash_files

PKG_DIR = Path(__file__).resolve().parent
DATA_DIR = PKG_DIR / "data"
PROMPT_FILES = ("code_system.md", "code_fewshot.json", "globals_system.md", "globals_fewshot.json")


@dataclass(frozen=True)
class Miti:
    data_dir: Path
    data: dict[str, Any]
    rating_schema: dict[str, Any]
    report: dict[str, Any]
    hash: str

    @classmethod
    def load(
        cls, data_dir: Path = DATA_DIR, rules_path: Path | None = PKG_DIR / "rules.py"
    ) -> "Miti":
        """Read the definition files. Hash order: pack.yaml, rules.py, rating schema, prompts
        (sorted), report.yaml (same bytes and order as the old pack loader)."""
        paths = [data_dir / "pack.yaml"]
        if rules_path is not None and rules_path.is_file():
            paths.append(rules_path)
        paths.append(data_dir / "rating.schema.json")
        if (data_dir / "prompts").is_dir():
            paths += sorted((data_dir / "prompts").glob("*"))
        paths.append(data_dir / "report.yaml")
        return cls(
            data_dir=data_dir,
            data=yaml.safe_load((data_dir / "pack.yaml").read_text()),
            rating_schema=json.loads((data_dir / "rating.schema.json").read_text()),
            report=yaml.safe_load((data_dir / "report.yaml").read_text()),
            hash=hash_files(paths),
        )

    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def version(self) -> str:
        return self.data["version"]

    @property
    def pack_format(self) -> str:
        return self.data["pack_format"]

    @property
    def items(self) -> list[dict[str, Any]]:
        return self.data["items"]

    @property
    def prompt_paths(self) -> list[Path]:
        return [self.data_dir / "prompts" / n for n in PROMPT_FILES]

    def facts(self) -> PackFacts:
        return PackFacts(id=self.id, version=self.version, hash=self.hash)


MITI = Miti.load()
