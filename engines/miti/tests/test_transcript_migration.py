"""MITI does not retain compatibility exports for shared transcript types."""

import importlib.util
from importlib.resources import files


def test_miti_has_no_transcript_reexports_or_moved_files():
    import onolys_miti
    import onolys_miti.transcript as miti_transcript

    for name in ("Turn", "Transcript", "TranscriptTurnV1", "TranscriptV1"):
        assert not hasattr(onolys_miti, name)
        assert not hasattr(miti_transcript, name)
    assert miti_transcript.Span.__module__ == "onolys_miti.transcript"
    for module in ("transcript_v1", "transcript_input", "transcript_txt"):
        assert importlib.util.find_spec(f"onolys_miti.{module}") is None
    assert not files("onolys_miti").joinpath("data/transcript.v1.schema.json").is_file()
