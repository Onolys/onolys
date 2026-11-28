"""The terminal `cancelled` state and the fields that remember its result."""

from datetime import UTC, datetime

import pytest

from onolys_api.jobs import machine as m
from onolys_api.repo.models import SessionDoc, SessionStatusDoc
from onolys_api.routes.sessions import SessionListItem

CANCELLABLE = (
    "created", "uploading", "upload_incomplete", "validating", "transcribing",
    "awaiting_input", "running",
)  # fmt: skip


@pytest.mark.parametrize("state", CANCELLABLE)
def test_in_progress_states_may_cancel(state):
    assert "cancelled" in m.TRANSITIONS[state]


@pytest.mark.parametrize("state", ["report_ready", "failed"])
def test_report_ready_and_failed_may_not_cancel(state):
    assert "cancelled" not in m.TRANSITIONS[state]


def test_cancelled_goes_only_to_deleting():
    assert m.TRANSITIONS["cancelled"] == frozenset({"deleting"})


def test_cancelled_is_in_not_deleting():
    assert "cancelled" in m._NOT_DELETING
    assert "cancelled" in m.STATES


def test_status_fields_include_counted():
    assert "counted" in m.STATUS_FIELDS


def test_session_doc_round_trips_with_and_without_cancel():
    assert SessionDoc(uid="u").cancel is None
    at = datetime(2026, 11, 24, tzinfo=UTC)
    doc = SessionDoc(uid="u", state="cancelled", cancel={"counted": True, "units": 1, "at": at})
    back = SessionDoc.model_validate(doc.to_store())
    assert back.cancel is not None
    assert (back.cancel.counted, back.cancel.units, back.cancel.at) == (True, 1, at)
    assert SessionDoc.model_validate(SessionDoc(uid="u").to_store()).cancel is None


def test_status_doc_round_trips_with_and_without_counted():
    s = SessionStatusDoc(uid="u", state="cancelled", counted=False)
    assert SessionStatusDoc.model_validate(s.to_store()).counted is False
    assert SessionStatusDoc.model_validate(SessionStatusDoc(uid="u").to_store()).counted is None


def test_list_item_accepts_cancelled():
    item = SessionListItem(id="s", status="cancelled", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert item.status == "cancelled"
