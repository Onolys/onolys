from unittest.mock import patch

from onolys_api.config import Settings
from onolys_api.repo.firestore import make_firestore_client


def test_client_honours_firestore_database_and_project():
    with patch("onolys_api.repo.firestore.firestore.Client") as C:
        make_firestore_client(
            Settings(
                env="staging", auth_mode="idp", gcp_project="onolys", firestore_database="staging"
            )
        )
    kw = C.call_args.kwargs
    assert kw["project"] == "onolys" and kw["database"] == "staging"


def test_client_default_database(monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    with patch("onolys_api.repo.firestore.firestore.Client") as C:
        make_firestore_client(Settings(env="local", gcp_project="p"))
    assert C.call_args.kwargs["database"] == "(default)"


def test_client_uses_anonymous_credentials_with_emulator(monkeypatch):
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
    with patch("onolys_api.repo.firestore.firestore.Client") as C:
        make_firestore_client(Settings(env="test", gcp_project=""))
    kw = C.call_args.kwargs
    assert kw["project"] == "demo-onolys"
    assert type(kw["credentials"]).__name__ == "AnonymousCredentials"


def test_uid_locks_are_shared_while_held_and_evicted_when_idle():
    import gc
    from unittest.mock import MagicMock

    from onolys_api.repo.firestore import FirestoreRepo

    repo = FirestoreRepo(MagicMock(), MagicMock())
    a = repo._uid_lock("u1")
    assert repo._uid_lock("u1") is a  # same uid while held: one lock
    assert repo._uid_lock("u2") is not a
    del a
    gc.collect()
    assert "u1" not in repo._uid_locks
