"""04-cancel Task 2: `decide_cancel`, the pure charge rule for a cancel (PRD R4)."""

import pytest

from onolys_api.jobs import charging
from onolys_api.repo import limits
from onolys_api.repo.limits import CancelCharge, decide_cancel


def test_reexported_from_charging():
    assert charging.decide_cancel is limits.decide_cancel


# (state, stt_operation set, run counted (None: no run reserved), interview_id) -> (units, counted)
ROWS = [
    ("created", False, None, None, 0, False),
    ("uploading", False, None, None, 0, False),
    ("upload_incomplete", False, None, None, 0, False),
    ("validating", False, None, None, 0, False),
    ("transcribing", False, None, None, 0, False),  # no operation submitted yet
    ("transcribing", True, None, None, 1, True),  # Chirp job submitted
    ("awaiting_input", True, None, None, 1, True),
    ("awaiting_input", False, None, None, 1, True),  # transcription done: operation irrelevant
    ("running", False, True, None, 0, True),  # run's counted reported, no new charge
    ("running", False, False, None, 0, False),
    ("running", False, None, None, 0, False),  # no run info: nothing counted
    # interview-linked sessions are exempt everywhere
    ("created", False, None, "i1", 0, False),
    ("validating", False, None, "i1", 0, False),
    ("transcribing", False, None, "i1", 0, False),
    ("transcribing", True, None, "i1", 0, False),
    ("awaiting_input", True, None, "i1", 0, False),
    ("running", False, False, "i1", 0, False),
    ("running", False, True, "i1", 0, False),
]


@pytest.mark.parametrize(("state", "op", "run_counted", "interview_id", "units", "counted"), ROWS)
def test_r4_table(state, op, run_counted, interview_id, units, counted):
    got = decide_cancel(state, op, run_counted, interview_id)
    assert got == CancelCharge(units, counted)
    assert (got.units, got.counted) == (units, counted)


def test_unit_is_always_one_never_n_runs():
    # no n_runs input exists, and a charged cancel costs exactly 1
    assert decide_cancel("awaiting_input", False, None, None).units == 1
    assert decide_cancel("transcribing", True, None, None).units == 1


@pytest.mark.parametrize("state", ["report_ready", "failed", "cancelled", "deleting"])
def test_non_cancellable_state_is_rejected(state):
    with pytest.raises(ValueError):
        decide_cancel(state, True, None, None)
