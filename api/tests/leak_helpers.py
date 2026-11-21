"""Reusable leak scan for scenario secrets (ai-interview PRD AC2).

`secret_strings(scenario)` lists what must never leave the server; `find_leaks(text, scenario)`
returns the ones found in any text. Task 5 applies it to relay -> client frames (decode text
frames, scan JSON/str of every frame); Task 2 applies it to /v1 responses and captured logs.
"""

import re
from typing import Any

# Distinctive hidden facts, matched case-insensitively beyond the full strings (cheap paraphrase net).
HIDDEN_PHRASES = ("cyclist", "near-miss", "neighbour", "4 pm", "empty bottles")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 20]


def secret_strings(sc: dict[str, Any]) -> list[str]:
    out = [sc["hidden_info"], *_sentences(sc["hidden_info"]), *sc["response_rules"]]
    out += [sc["persona"]["situation"], *HIDDEN_PHRASES]
    return out


def find_leaks(text: str, sc: dict[str, Any]) -> list[str]:
    low = text.lower()
    return [s for s in secret_strings(sc) if s.lower() in low]
