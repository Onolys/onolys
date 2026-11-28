"""Deterministic generator of the synthetic compare scenarios.

Run `python eval/fixtures/compare/builder.py` to rewrite the committed `<scenario>.json` files; a
test fails when they drift from this code. Every text is invented placeholder text
("Synthetic clinician turn 3."); nothing is copied from a dataset.
"""
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compare.fakes import SCENARIOS, FakePriceBook

UID = "synthetic-uid"
BASE = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
COUNT_IDS = ("gi", "persuade", "persuade_permission", "question", "sr", "cr", "affirm",
             "seek_collab", "emphasize_autonomy", "confront")
GLOBAL_IDS = ("cct", "sst", "partnership", "empathy")
PRICES = {
    "claude/synthetic-large": {"input_usd_per_million": 3.0, "output_usd_per_million": 15.0},
    "openai/synthetic-mid": {"input_usd_per_million": 1.0, "output_usd_per_million": 4.0},
    "gemini/synthetic-small": {"input_usd_per_million": 0.5, "output_usd_per_million": 2.0},
    # mistral/synthetic-unpriced is deliberately absent: cost must be n/a, never 0.
}
COMBOS = {
    "A": {"combo_key": "claude/synthetic-large/low", "engine": "miti", "provider": "claude",
          "litellm_id": "claude/synthetic-large", "effort": "low"},
    "B": {"combo_key": "openai/synthetic-mid/low", "engine": "oneshot:synthetic",
          "provider": "openai", "litellm_id": "openai/synthetic-mid", "effort": "low"},
    "C": {"combo_key": "gemini/synthetic-small/low", "engine": "miti", "provider": "gemini",
          "litellm_id": "gemini/synthetic-small", "effort": "low"},
    "U": {"combo_key": "mistral/synthetic-unpriced/low", "engine": "miti",
          "provider": "mistral", "litellm_id": "mistral/synthetic-unpriced", "effort": "low"},
}
PRICE_BOOK = FakePriceBook(PRICES)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def sid_of(idx):
    return f"synthetic-s{idx:02d}"


def dsid_of(idx):
    return f"syn-{idx:02d}"


def transcript_of(n_turns):
    turns = []
    for i in range(n_turns):
        clin = i % 2 == 0
        turns.append({"id": f"t{i + 1}", "speaker": "A" if clin else "B",
                      "role": "clinician" if clin else "client",
                      "text": f"Synthetic {'clinician' if clin else 'client'} turn {i + 1}.",
                      "start_ms": i * 10_000, "end_ms": i * 10_000 + 9_000})
    return {"language": "en", "duration_ms": n_turns * 10_000, "turns": turns}


def demo_counts(i, ci):
    """Human counts for session i, and a deterministic +-1 offset per combo index ci."""
    human = {"gi": 1 + i % 2, "persuade": 0, "persuade_permission": int(i % 3 == 0),
             "question": 3 + i % 4, "sr": 1 + i % 3, "cr": i % 3, "affirm": 1,
             "seek_collab": i % 2, "emphasize_autonomy": 0, "confront": 0}
    ours = {k: max(0, v + (i + ci * 2 + n) % 3 - 1) for n, (k, v) in enumerate(human.items())}
    return human, ours


def demo_globals(i, ci):
    human = {k: 3 + (i + n) % 3 for n, k in enumerate(GLOBAL_IDS)}
    ours = {k: min(5, max(1, v + (i + ci + n) % 3 - 1)) for n, (k, v) in enumerate(human.items())}
    return human, ours


class Scenario:
    def __init__(self, name, dataset_id, *, status="done", repeats=1, combos=("A",),
                 cancelled_at=None, description=""):
        self.name, self.dataset_id, self.status, self.repeats = name, dataset_id, status, repeats
        self.combos = list(combos)
        self.cancelled_at, self.description = cancelled_at, description
        self.sessions, self.cells, self.run_docs, self.reports = {}, [], {}, {}
        self.gold, self.transcripts, self.provider_skips = {}, {}, []
        self._order = {}

    # -- sessions -----------------------------------------------------------------------------
    def add_session(self, idx, *, n_turns=6, span=None, counts=None, globals_=None, utt=None,
                    quality_label=None, partial_counts=None):
        from onolys_eval._formulas import compute_summaries
        from onolys_eval.gold import Gold
        transcript = transcript_of(n_turns)
        span = span or (0, n_turns)
        raw = {"schema": "gold.v1", "dataset_id": self.dataset_id, "session_id": dsid_of(idx),
               "source": {"retrieved_at": "2026-11-01T00:00:00+00:00"},
               "coded_span": {"start_turn": span[0], "end_turn": span[1]},
               "counts": partial_counts if partial_counts is not None else (counts or {}),
               "globals": globals_, "parse": {"method": "auto", "warnings": []}}
        labeled_counts = {k: v for k, v in raw["counts"].items() if v is not None}
        if labeled_counts or globals_:
            raw["summaries"] = compute_summaries(labeled_counts, globals_ or {})
        if utt is not None:
            raw["utterance_codes"] = [{"turn_id": t, "codes": list(c)} for t, c in utt]
        if quality_label:
            raw["quality_label"] = quality_label
        gold = Gold.model_validate(raw).model_dump(mode="json", by_alias=True)
        gold_sha = sha(gold)
        self.gold[gold_sha] = gold
        doc = {"id": "", "sha256": sha(transcript), "language": "en", "transcript": transcript,
               "pointer": None, "created_at": iso(BASE)}
        doc.pop("id")
        self.transcripts[sid_of(idx)] = doc
        self.sessions[idx] = {"session_id": sid_of(idx), "uid": UID,
                              "dataset_session_id": dsid_of(idx), "gold_sha256": gold_sha,
                              "transcript_sha256": doc["sha256"], "_span": span,
                              "_n_turns": n_turns}

    # -- runs ---------------------------------------------------------------------------------
    def _instances(self, idx, counts, lines):
        sess = self.sessions[idx]
        turns = {t["id"]: t["text"] for t in self.transcripts[sid_of(idx)]["transcript"]["turns"]}
        if lines is None:
            cl = [f"t{i + 1}" for i in range(*sess["_span"]) if i % 2 == 0]
            lines = {c: [cl[(ci + k) % len(cl)] for k in range(counts[c])]
                     for ci, c in enumerate(COUNT_IDS)}
        out, n = {}, 0
        for code in COUNT_IDS:
            out[code] = []
            for turn in lines.get(code, []):
                n += 1
                text = turns[turn]
                out[code].append({"turn_id": turn, "start": 0, "end": len(text), "quote": text,
                                  "id": f"i{n}",
                                  "rationale": f"Synthetic rationale for {code} at {turn}."})
        return out

    def _report(self, idx, engine, counts, globals_, lines, withheld):
        if engine.startswith("oneshot:"):
            tips = [{"rank": 1, "item_id": "question", "observation": "Synthetic observation.",
                     "alternative": "Synthetic alternative.", "why_it_matters": "Synthetic reason."}]
            return {"counts": counts, "globals": globals_, "tips": tips}
        inst = self._instances(idx, counts, lines)
        if withheld:
            code, k = withheld
            inst[code][k]["rationale"] = ""
        sess = self.sessions[idx]
        turns = self.transcripts[sid_of(idx)]["transcript"]["turns"]
        ev = [{"turn_id": t["id"], "start": 0, "end": len(t["text"]), "quote": t["text"]}
              for t in turns[sess["_span"][0]:sess["_span"][1]][:2]]
        return {
            "schema_version": "synthetic-minimal",
            "behaviours": [{"item_id": c, "onolys_count": {"mean": float(counts[c]),
                            "min": float(counts[c]), "max": float(counts[c]),
                            "values": [float(counts[c])]},
                            "instances": inst[c], "instances_total": len(inst[c])}
                           for c in COUNT_IDS],
            "globals": [{"item_id": g, "onolys": {"score": globals_[g], "source": "model",
                         "reason": f"Synthetic reason for {g} score {globals_[g]}.",
                         "evidence": ev}} for g in GLOBAL_IDS],
        }

    def add_run(self, idx, combo, repeat=1, attempt=0, *, status="done", counts=None,
                globals_=None, lines=None, withheld=None, error=None, reported_cost=False,
                start_offset=0):
        c = COMBOS[combo]
        sess = self.sessions[idx]
        run_id = f"run-s{idx:02d}-{combo}{repeat}-a{attempt}"
        started = BASE + timedelta(minutes=30 * idx + 5 * "ABCU".index(combo) + repeat
                                   + start_offset + 10 * attempt)
        ended = started + timedelta(seconds=60 + 10 * (idx % 5))
        usage = {"input_tokens": 10_000 + 100 * idx, "output_tokens": 1_500, "calls": 1}
        if reported_cost:
            usage["cost_usd"] = round(0.001 * (idx + 1), 6)
        doc = {"change_goal": "Synthetic change goal.", "clinician_speaker": "A", "language": "en",
               "transcript_sha256": sess["transcript_sha256"],
               "coded_span": {"start_turn": sess["_span"][0], "end_turn": sess["_span"][1]},
               "uid": UID, "session_id": sid_of(idx), "run_id": run_id, "n_runs": 1,
               "code_version": "synthetic", "status": status, "attempts": attempt + 1,
               "started": iso(started), "ended": iso(ended), "error": error,
               "run_info": {"usage": usage},
               "eval": {"eval_run_id": f"eval-{self.name}", "combo_key": c["combo_key"],
                        "repeat": repeat, "engine": c["engine"], "route_override": None,
                        "resolved_route": {"litellm_id": c["litellm_id"], "effort": c["effort"]},
                        "engine_version": "synthetic"}}
        self.run_docs[run_id] = doc
        if status == "done":
            self.reports[run_id] = {
                "version": 1, "run_id": run_id, "pointer": None,
                "report_schema_version": "synthetic.v1",
                "report": self._report(idx, c["engine"], counts, globals_, lines, withheld)}
        self._cell(idx, combo, repeat, attempt, run_id, status, doc["started"], doc["ended"],
                   error, usage, c["litellm_id"])

    def add_placeholder(self, idx, combo, status, reason, repeat=1):
        c = COMBOS[combo]
        self._cell(idx, combo, repeat, 0, None, status, None, None, None, None, c["litellm_id"],
                   reason)

    def _cell(self, idx, combo, repeat, attempt, run_id, status, started, ended, error, usage,
              litellm_id, reason=None):
        sess = self.sessions[idx]
        run_info = None
        if usage is not None:
            run_info = {"usage": usage, "cost_usd_est": PRICE_BOOK.estimate(usage, litellm_id).cost_usd}
        self.cells.append({
            "sid": sess["session_id"], "dataset_session_id": sess["dataset_session_id"],
            "engine": COMBOS[combo]["engine"], "combo_key": COMBOS[combo]["combo_key"],
            "repeat": repeat, "attempt": attempt, "run_id": run_id, "status": status,
            "started": started, "ended": ended, "error": {"code": error} if error else None,
            "run_info": run_info,
            "gold_ref": {"sha256": sess["gold_sha256"], "path": f"gold/{sess['gold_sha256']}.json"},
            "_reason": reason or error, "_idx": idx, "_combo": combo})

    # -- output -------------------------------------------------------------------------------
    def to_dict(self):
        order = {c: n for n, c in enumerate(self.combos)}
        cells = sorted(self.cells, key=lambda x: (x["_idx"], order[x["_combo"]], x["repeat"],
                                                  x["attempt"]))
        runs = [{"session_id": x["sid"], "run_id": x["run_id"], "combo_key": x["combo_key"],
                 "repeat": x["repeat"], "attempt": x["attempt"], "status": x["status"],
                 "reason": x["_reason"]} for x in cells]
        cells = [{k: v for k, v in x.items() if not k.startswith("_")} for x in cells]
        sessions = [{k: v for k, v in self.sessions[i].items() if not k.startswith("_")}
                    for i in sorted(self.sessions)]
        return {
            "scenario": self.name, "synthetic": True, "description": self.description,
            "eval_run": {"eval_run_id": f"eval-{self.name}", "name": f"Synthetic {self.name}",
                         "dataset_id": self.dataset_id, "status": self.status,
                         "cancelled_at": self.cancelled_at, "repeats": self.repeats,
                         "change_goal": "Synthetic change goal.", "language": "en",
                         "combos": [COMBOS[c] for c in self.combos], "sessions": sessions,
                         "provider_skips": self.provider_skips, "runs": runs},
            "cells": cells, "run_docs": self.run_docs, "reports": self.reports,
            "transcripts": self.transcripts, "gold": self.gold, "prices": PRICES,
        }


def fill(sc, sessions, combos, repeats=1, *, skip=None):
    """Add demo gold plus one demo run per (session, combo, repeat); `skip(i, combo, rep)`
    returns True for cells the caller adds by hand."""
    for i in sessions:
        h, _ = demo_counts(i, 0)
        hg, _ = demo_globals(i, 0)
        sc.add_session(i, counts=h, globals_=hg)
    for i in sessions:
        for ci, combo in enumerate(combos):
            for rep in range(1, repeats + 1):
                if skip and skip(i, combo, rep):
                    continue
                _, ours = demo_counts(i, ci + 1)
                _, og = demo_globals(i, ci + 1)
                sc.add_run(i, combo, rep, counts=ours, globals_=og, reported_cost=(combo == "A" and i % 2 == 1))


H_COUNTS = {"gi": 1, "persuade": 0, "persuade_permission": 0, "question": 10, "sr": 2, "cr": 3,
            "affirm": 1, "seek_collab": 1, "emphasize_autonomy": 0, "confront": 0}


def counts_golden():
    sc = Scenario("counts_golden", "casaa-miti421-video2013", repeats=3, combos=("A", "B"),
                  description="Golden: human question 10, combo A repeats 8/10/12 -> session miss "
                  "1.33; s2 human question 6, A repeats 8/8/8 -> miss 2; off 1.67, n 2, repeats 3. "
                  "Globals repeats split into same/off1/off2plus. Combo B (oneshot) exact on s1, "
                  "cr+1 on s2; one retried attempt (s2 B repeat 2).")
    h2 = {**H_COUNTS, "question": 6}
    sc.add_session(1, n_turns=10, counts=H_COUNTS, globals_={"cct": 4, "sst": 4, "partnership": 3, "empathy": 4})
    sc.add_session(2, n_turns=10, counts=h2, globals_={"cct": 3, "sst": 3, "partnership": 3, "empathy": 3})
    g1 = {"cct": 4, "sst": 4, "partnership": 3, "empathy": 4}
    for rep, q in enumerate((8, 10, 12), 1):
        sc.add_run(1, "A", rep, counts={**H_COUNTS, "question": q},
                   globals_={**g1, "cct": (4, 4, 5)[rep - 1]}, reported_cost=True)
        sc.add_run(2, "A", rep, counts={**h2, "question": 8},
                   globals_={g: 3 for g in GLOBAL_IDS} | {"cct": (3, 4, 5)[rep - 1]})
        sc.add_run(1, "B", rep, counts=H_COUNTS, globals_=g1)
        if rep == 2:
            sc.add_run(2, "B", rep, 0, status="failed", error="provider_error")
            sc.add_run(2, "B", rep, 1, counts={**h2, "cr": 4}, globals_={g: 3 for g in GLOBAL_IDS})
        else:
            sc.add_run(2, "B", rep, counts={**h2, "cr": 4}, globals_={g: 3 for g in GLOBAL_IDS})
    return sc


def annomi_partial():
    sc = Scenario("annomi_partial", "annomi", repeats=2, combos=("A", "B"),
                  description="AnnoMI-style partial gold: only question/sr/cr/gi labeled (others "
                  "omitted or null), no globals. s1 SR=3 CR=1 Q=2 -> R:Q 2.0, %CR 0.25. s2: combo A "
                  "repeat 2 has Question 0 (division by zero). s3: human Question 0 "
                  "(undefined human R:Q). Utterance codes, one code per turn (grouping caveat).")
    sc.add_session(1, n_turns=14, partial_counts={"question": 2, "sr": 3, "cr": 1, "gi": 1,
                   "affirm": None}, utt=[(f"t{2 * k + 1}", c) for k, c in enumerate(
                   [["question"], ["question"], ["sr"], ["sr"], ["sr"], ["cr"], ["gi"]])])
    sc.add_session(2, n_turns=12, partial_counts={"question": 2, "sr": 2, "cr": 1, "gi": 0,
                   "persuade": None}, utt=[(f"t{2 * k + 1}", c) for k, c in enumerate(
                   [["question"], ["sr"], ["question"], ["sr"], ["cr"], []])])
    sc.add_session(3, n_turns=6, partial_counts={"question": 0, "sr": 1, "cr": 1, "gi": 0},
                   utt=[("t1", ["sr"]), ("t3", ["cr"]), ("t5", [])])
    mine = {1: {"question": 2, "sr": 3, "cr": 1, "gi": 1},
            2: {"question": 2, "sr": 2, "cr": 1, "gi": 0},
            3: {"question": 0, "sr": 1, "cr": 1, "gi": 0}}
    g = {k: 3 for k in GLOBAL_IDS}
    for i in (1, 2, 3):
        for rep in (1, 2):
            full = {c: 0 for c in COUNT_IDS} | mine[i]
            a = dict(full)
            if i == 2 and rep == 2:
                a["question"] = 0
            sc.add_run(i, "A", rep, counts=a, globals_=g)
            sc.add_run(i, "B", rep, counts=full, globals_=g)
    return sc


def lines():
    sc = Scenario("lines", "casaa-miti421-video2013", repeats=2, combos=("A", "B"),
                  description="Line alignment. s1: 12 turns, coded span turns 1..11 (t1 outside, "
                  "no gold row), multi-code gold turn t7 (cr+affirm). Combo A repeat 1 misses "
                  "affirm@t7; repeat 2 mislabels sr@t5 as cr, adds cr+affirm@t7 (multi both "
                  "sides), misses gi@t11. s2: 8 turns, single codes; A repeat 2 misses t7. One "
                  "withheld rationale (''). Combo B (oneshot) has no instances.")
    u1 = [("t3", ["question"]), ("t5", ["sr"]), ("t7", ["cr", "affirm"]),
          ("t9", ["question"]), ("t11", ["gi"])]
    c1 = {"gi": 1, "question": 2, "sr": 1, "cr": 1, "affirm": 1}
    u2 = [("t1", ["question"]), ("t3", ["sr"]), ("t5", ["cr"]), ("t7", ["confront"])]
    c2 = {"question": 1, "sr": 1, "cr": 1, "confront": 1}
    g = {"cct": 4, "sst": 4, "partnership": 4, "empathy": 4}
    sc.add_session(1, n_turns=12, span=(1, 12), counts={c: 0 for c in COUNT_IDS} | c1, globals_=g, utt=u1)
    sc.add_session(2, n_turns=8, counts={c: 0 for c in COUNT_IDS} | c2, globals_=g, utt=u2)

    def counts_of(ln):
        return {c: len(ln.get(c, [])) for c in COUNT_IDS}
    runs = {
        (1, 1): {"question": ["t3", "t9"], "sr": ["t5"], "cr": ["t7"], "gi": ["t11"]},
        (1, 2): {"question": ["t3", "t9"], "cr": ["t5", "t7"], "affirm": ["t7"]},
        (2, 1): {"question": ["t1"], "sr": ["t3"], "cr": ["t5"], "confront": ["t7"]},
        (2, 2): {"question": ["t1"], "sr": ["t3"], "cr": ["t5"]},
    }
    for (i, rep), ln in runs.items():
        sc.add_run(i, "A", rep, counts=counts_of(ln), globals_=g, lines=ln,
                   withheld=("question", 0) if (i, rep) == (1, 1) else None)
        human = c1 if i == 1 else c2
        sc.add_run(i, "B", rep, counts={c: 0 for c in COUNT_IDS} | human, globals_=g)
    return sc


def twelve_sessions():
    sc = Scenario("twelve_sessions", "casaa-miti421-video2013", status="partial",
                  combos=("A", "B", "U"),
                  description="12 sessions x 3 combos, 1 repeat. Combo A failed (2 attempts) in "
                  "session 5 -> 11 paired of 12; real zero counts (human 0 and ours 0; human 1 and "
                  "ours 0). B retried in s3 (attempt 0 failed). Combo U has no price (cost n/a); "
                  "A reports cost_usd on odd sessions, others priced from tokens.")
    fill(sc, range(1, 13), ("A", "B", "U"),
         skip=lambda i, c, r: (i == 5 and c == "A") or (i == 3 and c == "B"))
    sc.add_run(5, "A", 1, 0, status="failed", error="invalid_output")
    sc.add_run(5, "A", 1, 1, status="failed", error="invalid_output")
    sc.add_run(3, "B", 1, 0, status="failed", error="provider_error")
    _, ours = demo_counts(3, 2)
    _, og = demo_globals(3, 2)
    sc.add_run(3, "B", 1, 1, counts=ours, globals_=og)
    return sc


def cancelled_partial():
    sc = Scenario("cancelled_partial", "casaa-miti421-video2013", status="partial",
                  combos=("A", "B"), cancelled_at="2026-11-20T12:30:00Z",
                  description="Cancel after 4 of 12 sessions: s1-s3 both combos done, s4 only A "
                  "done (B cancelled), s5-s12 cancelled. Cancelled cells have no run doc.")
    fill(sc, range(1, 13), ("A", "B"), skip=lambda i, c, r: i > 4 or (i == 4 and c == "B"))
    for i in range(4, 13):
        for c in ("B",) if i == 4 else ("A", "B"):
            sc.add_placeholder(i, c, "cancelled", "cancelled")
    return sc


def provider_skipped():
    sc = Scenario("provider_skipped", "casaa-miti421-video2013", status="partial",
                  combos=("A", "B", "C"),
                  description="12 sessions x 3 combos. Gemini combo C: sessions 1-5 failed "
                  "(provider_error), sessions 6-12 skipped (provider_unavailable) after 5 "
                  "failures in a row. A and B complete on all 12.")
    fill(sc, range(1, 13), ("A", "B"))
    for i in range(1, 6):
        sc.add_run(i, "C", 1, 0, status="failed", error="provider_error")
    for i in range(6, 13):
        sc.add_placeholder(i, "C", "skipped", "provider_unavailable")
    sc.provider_skips = [{"provider": "gemini", "after_failures": 5,
                          "skipped_at": "2026-11-20T13:00:00Z"}]
    return sc


def _no_labels(name, dataset, quality):
    sc = Scenario(name, dataset, combos=("A", "B"),
                  description=f"{dataset}: gold has no counts, globals or line labels"
                  + (" (only quality_label high/low)." if quality else " (nothing labeled)."))
    for i, label in ((1, "high"), (2, "low")):
        sc.add_session(i, quality_label=label if quality else None)
        _, ours = demo_counts(i, 1)
        _, og = demo_globals(i, 1)
        sc.add_run(i, "A", 1, counts=ours, globals_=og)
        sc.add_run(i, "B", 1, counts=ours, globals_=og)
    return sc


def no_completed():
    sc = Scenario("no_completed", "casaa-miti421-video2013", status="cancelled",
                  combos=("A", "B"), cancelled_at="2026-11-20T10:20:00Z",
                  description="No done run: A failed in s1 (2 attempts), everything else cancelled.")
    for i in (1, 2, 3):
        h, _ = demo_counts(i, 0)
        sc.add_session(i, counts=h, globals_=demo_globals(i, 0)[0])
    sc.add_run(1, "A", 1, 0, status="failed", error="invalid_output")
    sc.add_run(1, "A", 1, 1, status="failed", error="invalid_output")
    for i, combos in ((1, "B"), (2, "AB"), (3, "AB")):
        for c in combos:
            sc.add_placeholder(i, c, "cancelled", "cancelled")
    return sc


def running():
    sc = Scenario("running", "casaa-miti421-video2013", status="running", combos=("A",),
                  description="Not finished: s1 done, s2 running, s3 queued.")
    for i in (1, 2, 3):
        h, ours = demo_counts(i, 1)
        hg, og = demo_globals(i, 1)
        sc.add_session(i, counts=h, globals_=hg)
        if i == 1:
            sc.add_run(i, "A", 1, counts=ours, globals_=og)
    sc.add_placeholder(2, "A", "running", None)
    sc.add_placeholder(3, "A", "queued", None)
    return sc


def scale(n_sessions=166, combos=("A", "B", "C")):
    """In-memory only (not committed): <= 499 runs for the payload-size and timing tests."""
    sc = Scenario("scale", "casaa-miti421-video2013", combos=combos,
                  description="Generated; 166 sessions x 3 combos = 498 runs.")
    fill(sc, range(1, n_sessions + 1), combos)
    return sc


BUILDERS = {
    "counts_golden": counts_golden, "annomi_partial": annomi_partial, "lines": lines,
    "twelve_sessions": twelve_sessions, "cancelled_partial": cancelled_partial,
    "provider_skipped": provider_skipped,
    "no_labels_hlqc": lambda: _no_labels("no_labels_hlqc", "hlqc", True),
    "no_labels_phac": lambda: _no_labels("no_labels_phac", "phac-en", False),
    "no_completed": no_completed, "running": running,
}
assert tuple(BUILDERS) == SCENARIOS


def build(name):
    return BUILDERS[name]().to_dict()


def render(data):
    """Top-level keys on their own line, values compact: reviewable and under the size cap."""
    body = ",\n".join(f"{json.dumps(k)}:{json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False)}"
                      for k, v in data.items())
    return "{\n" + body + "\n}\n"


def main():
    here = Path(__file__).resolve().parent
    for name in SCENARIOS:
        (here / f"{name}.json").write_text(render(build(name)))
        print("wrote", name)


if __name__ == "__main__":
    main()
