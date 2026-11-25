"""Informational clinician-word coverage of located evidence, independent of scoring."""

import re
from typing import TypedDict

from onolys_miti.prepare import Volley
from onolys_miti.result import Instance


class WordCoverage(TypedDict):
    clinician_words: int
    covered_words: int
    residual_words: int


class VolleyCoverage(WordCoverage):
    volley_id: str


class Coverage(WordCoverage):
    volleys: list[VolleyCoverage]


def coverage(volleys: list[Volley], instances: list[Instance]) -> Coverage:
    """Count each whitespace word once if any located span overlaps it.

    Uncoded and down-counted evidence covers words too. Only clinician turns in the
    supplied volleys contribute; client context never contributes to the residual.
    """
    by_turn: dict[str, list[tuple[int, int]]] = {}
    for inst in instances:
        if inst.start < inst.end:
            by_turn.setdefault(inst.turn_id, []).append((inst.start, inst.end))
    rows: list[VolleyCoverage] = []
    for volley in volleys:
        total = covered = 0
        for turn in volley.turns:
            spans = by_turn.get(turn.id, [])
            for word in re.finditer(r"\S+", turn.text):
                total += 1
                covered += any(a < word.end() and b > word.start() for a, b in spans)
        rows.append(VolleyCoverage(
            volley_id=volley.id,
            clinician_words=total,
            covered_words=covered,
            residual_words=total - covered,
        ))
    return Coverage(
        clinician_words=sum(r["clinician_words"] for r in rows),
        covered_words=sum(r["covered_words"] for r in rows),
        residual_words=sum(r["residual_words"] for r in rows),
        volleys=rows,
    )
