"""Prompt hashes for the report's `run_info.evaluation`: the tips prompt file (by file name) and
the engine-owned templates (`engine:*`), so a template change shows even when the definition is
unchanged. Text never enters `run_info`, only hashes."""

import hashlib

from onolys_miti import miti, tips
from onolys_miti.compare import template_strings
from onolys_miti.run_info import hash_files


def _sha(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def evaluation_prompt_hashes() -> dict[str, str]:
    return {
        tips.PROMPT_FILE: hash_files([miti.MITI.data_dir / "prompts" / tips.PROMPT_FILE]),
        "engine:tips_output_format": _sha(tips._OUTPUT_FORMAT),
        "engine:compare_templates": _sha(*template_strings()),
    }
