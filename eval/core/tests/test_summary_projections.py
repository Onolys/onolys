"""Report parsing, gold and transcript projections (pure, synthetic fixtures)."""
import copy

import pytest
from compare.fakes import FakeEvalRunSource
from onolys_eval.summary.projections import (
    TranscriptChanged,
    label_coverage,
    parse_report,
    project_gold,
    project_transcript,
)

UID = "synthetic-uid"


def _src(name):
    return FakeEvalRunSource.from_names(name)


def _run(src, eval_run_id, engine):
    for r in src.eval_run(eval_run_id)["runs"]:
        if r["status"] != "done":
            continue
        doc = src.run_doc(UID, r["session_id"], r["run_id"])
        if doc["eval"]["engine"].startswith(engine):
            return doc, src.report(UID, r["session_id"], r["run_id"])
    raise AssertionError(engine)


def test_miti_report_counts_globals_lines_and_reasons():
    src = _src("lines")
    eid = next(iter(src._by_id))
    doc, rep = _run(src, eid, "miti")
    run = parse_report(doc["eval"]["engine"], rep)
    assert run.status == "ok" and run.reason is None and run.has_lines
    assert all(isinstance(v, int) for v in run.counts.values())
    assert set(run.globals) == {"cct", "sst", "partnership", "empathy"}
    assert run.global_reasons["cct"].reason.startswith("Synthetic reason")
    assert run.global_reasons["cct"].evidence
    body = rep["report"]["behaviours"]
    total = sum(len(b["instances"]) for b in body)
    assert len(run.instances) == total
    # code = owning item_id; turn -> codes (multi-code turns)
    some = next(b for b in body if b["instances"])
    first = some["instances"][0]
    assert some["item_id"] in run.turn_codes[first["turn_id"]]


def test_withheld_rationale_kept_empty_and_separate():
    src = _src("lines")
    _doc, rep = _run(src, next(iter(src._by_id)), "miti")
    run = parse_report("miti", rep)
    assert not hasattr(run.instances[0], "rationale")
    assert "" in run.rationales.values()  # withheld stays "", never filled
    assert any(v.startswith("Synthetic rationale") for v in run.rationales.values())


def test_oneshot_routes_to_oneshot_scores_no_lines():
    src = _src("lines")
    doc, rep = _run(src, next(iter(src._by_id)), "oneshot")
    run = parse_report(doc["eval"]["engine"], rep)
    assert run.status == "ok" and not run.has_lines
    assert run.instances == () and run.turn_codes == {} and run.global_reasons == {}
    assert len(run.counts) == 10 and len(run.globals) == 4


def test_engine_routing_is_by_engine_not_shape():
    src = _src("lines")
    eid = next(iter(src._by_id))
    _, miti_rep = _run(src, eid, "miti")
    _, one_rep = _run(src, eid, "oneshot")
    assert parse_report("oneshot:synthetic", miti_rep).status == "unparseable"
    assert parse_report("miti", one_rep).status == "unparseable"
    bad = parse_report("mystery", miti_rep)
    assert bad.status == "unparseable" and bad.reason == "unknown_engine"


def _miti():
    src = _src("lines")
    return _run(src, next(iter(src._by_id)), "miti")[1]


def test_fail_closed_non_integer_count():
    rep = copy.deepcopy(_miti())
    rep["report"]["behaviours"][0]["onolys_count"]["mean"] = 2.5
    run = parse_report("miti", rep)
    assert run.status == "unparseable" and run.reason == "non_integer_count"
    assert run.counts == {} and run.instances == ()


def test_fail_closed_null_global_and_schema_mismatch():
    rep = copy.deepcopy(_miti())
    rep["report"]["globals"][0]["onolys"]["score"] = None
    assert parse_report("miti", rep).reason == "null_global"
    rep = copy.deepcopy(_miti())
    del rep["report"]["behaviours"]
    assert parse_report("miti", rep).reason == "schema_mismatch"
    assert parse_report("miti", {"nope": 1}).reason == "schema_mismatch"


def test_gold_projection_allowed_fields_only():
    src = _src("annomi_partial")
    eid = next(iter(src._by_id))
    sess = src.eval_run(eid)["sessions"][0]
    g = project_gold(src.gold(sess["gold_sha256"]))
    d = g.to_dict()
    assert set(d) == {"coded_span", "counts", "globals", "quality_label", "utterance_codes"}
    assert "source" not in d and "parse" not in d
    assert not hasattr(g, "source") and not hasattr(g, "parse")
    assert set(d["counts"]) <= {"question", "sr", "cr", "gi"}  # labeled only
    assert all(v is not None for v in d["counts"].values())
    assert d["globals"] == {}
    assert d["utterance_codes"] and set(d["utterance_codes"][0]) == {"turn_id", "codes", "note"}


def test_gold_projection_no_labels_hlqc():
    src = _src("no_labels_hlqc")
    sess = src.eval_run(next(iter(src._by_id)))["sessions"][0]
    g = project_gold(src.gold(sess["gold_sha256"]))
    assert g.counts == {} and g.globals == {} and g.utterance_codes is None
    assert g.quality_label in ("high", "low")


def test_label_coverage_table():
    c = label_coverage("casaa-miti421-video2013")
    assert len(c.counts) == 10 and len(c.globals) == 4 and c.line_labels
    assert label_coverage("annomi").counts == ("gi", "cr", "sr", "question") or set(
        label_coverage("annomi").counts) == {"question", "sr", "cr", "gi"}
    assert label_coverage("annomi").globals == ()
    assert "seek_collab" not in label_coverage("automisc-human").counts
    assert len(label_coverage("welivita-mi").counts) == 9
    assert label_coverage("annosum-mi").globals == ("empathy",)
    assert not label_coverage("hlqc").line_labels and label_coverage("hlqc").counts == ()
    assert label_coverage("phac-fr").counts == ()
    assert label_coverage("mi-tags-sample").counts.__len__() == 7
    assert label_coverage("nope-unknown") is None


def _tx(name="lines"):
    src = _src(name)
    eid = next(iter(src._by_id))
    sess = src.eval_run(eid)["sessions"][0]
    run = next(r for r in src.eval_run(eid)["runs"] if r["session_id"] == sess["session_id"]
               and r["status"] == "done")
    return src.run_doc(UID, sess["session_id"], run["run_id"]), src.transcript(
        UID, sess["session_id"])


def test_transcript_projected_to_coded_span_with_is_clinician():
    doc, tdoc = _tx()
    turns = project_transcript(doc, tdoc)
    span = doc["coded_span"]
    assert [t.id for t in turns] == [f"t{i + 1}" for i in range(span["start_turn"], span["end_turn"])]
    first = turns[0]
    assert first.is_clinician == (first.speaker == doc["clinician_speaker"])
    assert any(t.is_clinician for t in turns) and any(not t.is_clinician for t in turns)
    assert set(first.to_dict()) == {"id", "speaker", "is_clinician", "text", "start_ms", "end_ms"}


def test_transcript_sha_mismatch_signalled():
    doc, tdoc = _tx()
    tdoc = dict(tdoc, sha256="0" * 64)
    with pytest.raises(TranscriptChanged):
        project_transcript(doc, tdoc)


def test_transcript_time_span_and_no_span():
    doc, tdoc = _tx()
    doc = dict(doc, coded_span={"start_ms": 10_000, "end_ms": 30_000})
    assert [t.id for t in project_transcript(doc, tdoc)] == ["t2", "t3"]
    doc = dict(doc, coded_span=None)
    assert len(project_transcript(doc, tdoc)) == len(tdoc["transcript"]["turns"])


def test_multi_code_turn_maps_to_all_owning_codes():
    src = _src("lines")
    sc = next(iter(src._by_id.values()))
    rep = sc["reports"]["run-s01-A2-a0"]
    run = parse_report("miti", rep)
    assert len(run.turn_codes["t7"]) >= 2
    owners = {b["item_id"] for b in rep["report"]["behaviours"]
              if any(i["turn_id"] == "t7" for i in b["instances"])}
    assert run.turn_codes["t7"] == frozenset(owners)


def test_transcript_time_span_uses_overlap_boundaries_and_keeps_untimed_turns():
    doc, tdoc = _tx()
    times = [(0, 10), (5, 15), (10, 20), (20, 30), (None, None), (15, None), (10, None)]
    turns = [{"id": f"t{i}", "speaker": "A", "text": "Synthetic turn.",
              "start_ms": start, "end_ms": end} for i, (start, end) in enumerate(times)]
    tdoc = dict(tdoc, transcript={"turns": turns})
    doc = dict(doc, coded_span={"start_ms": 10, "end_ms": 20})
    assert [t.id for t in project_transcript(doc, tdoc)] == ["t1", "t2", "t4", "t5"]


def test_transcript_time_span_rejects_fully_untimed_transcript():
    from onolys_engine_core.errors import InvalidCodedSpan

    doc, tdoc = _tx()
    tdoc = dict(tdoc, transcript={"turns": [
        {"id": "untimed", "speaker": "A", "text": "Synthetic untimed turn."}]})
    doc = dict(doc, coded_span={"start_ms": 10, "end_ms": 20})
    with pytest.raises(InvalidCodedSpan, match="time spans require turn timestamps"):
        project_transcript(doc, tdoc)
