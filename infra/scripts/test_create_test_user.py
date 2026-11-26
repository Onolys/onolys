"""Tests for create-test-user.py (fake client, no network). Run: python3 -m pytest infra/scripts/test_create_test_user.py -q"""
import importlib.util
import pathlib
import re

import pytest

spec = importlib.util.spec_from_file_location("create_test_user", pathlib.Path(__file__).with_name("create-test-user.py"))
ctu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctu)


class Fake:
    def __init__(self, existing=()):
        self.existing = {e: f"uid-{e}" for e in existing}
        self.created = []
        self.updated = []

    def lookup(self, email):
        return self.existing.get(email)

    def create(self, email, password):
        self.created.append((email, password))
        return "uid-1"

    def update(self, uid, password):
        self.updated.append((uid, password))


def run(args, client, capsys, env=None, prompt=None):
    rc = ctu.main(args, client=client, env=env or {}, prompt=prompt or (lambda: pytest.fail("prompted")))
    return rc, capsys.readouterr()


def test_generated_email_format(capsys):
    c = Fake()
    rc, out = run([], c, capsys)
    assert rc == 0
    assert re.fullmatch(r"test-onolys-[0-9a-f]{8}@onolys\.com", c.created[0][0])


def test_generated_password_meets_policy(capsys):
    for _ in range(50):
        assert ctu.password_errors(ctu.generate_password()) == []
        assert len(ctu.generate_password()) >= 16


def test_default_project_is_eval():
    assert ctu.DEFAULT_PROJECT == "onolys-eval"


@pytest.mark.parametrize("project", ["onolys", "onolys-prod", "1054076260967", " Onolys "])
def test_prod_project_refused(project, capsys):
    c = Fake()
    rc, out = run(["--project", project, "--email", "a@b.co", "--password", "Sup3rSecret!"], c, capsys)
    assert rc == 2 and "prod" in out.err.lower()
    assert c.created == [] and c.updated == []


@pytest.mark.parametrize("project", ["onolys-eval", "onolys-staging", "my-sandbox"])
def test_non_prod_projects_allowed(project):
    assert ctu.project_errors(project) == []


def test_create_payload_is_verified_and_sends_nothing_by_email():
    assert ctu.create_payload("a@b.co", "pw123456") == {"email": "a@b.co", "password": "pw123456", "emailVerified": True}
    assert ctu.update_payload("uid-9", "pw123456") == {"localId": "uid-9", "password": "pw123456", "emailVerified": True}


def test_create_with_env_password_does_not_print_it(capsys):
    c = Fake()
    rc, out = run(["--email", "a@b.co"], c, capsys, env={"ONOLYS_ACCOUNT_PASSWORD": "FromEnv-12345"})
    assert rc == 0 and c.created == [("a@b.co", "FromEnv-12345")]
    assert out.out == "email: a@b.co\nproject: onolys-eval\n" and "FromEnv" not in out.err


def test_prompt_used_when_email_given_without_password(capsys):
    c = Fake()
    rc, out = run(["--email", "a@b.co"], c, capsys, prompt=lambda: "Prompted-12345")
    assert rc == 0 and c.created == [("a@b.co", "Prompted-12345")]
    assert "Prompted" not in out.out


def test_generated_password_printed(capsys):
    c = Fake()
    rc, out = run(["--email", "a@b.co", "--generate"], c, capsys)
    assert rc == 0 and f"password: {c.created[0][1]}" in out.out


def test_existing_email_errors_without_modifying(capsys):
    c = Fake(existing={"a@b.co"})
    rc, out = run(["--email", "a@b.co", "--password", "longEnough1"], c, capsys)
    assert rc == 1
    assert "already exists" in out.err and "--update" in out.err
    assert c.created == [] and c.updated == []
    assert out.out == ""


def test_update_sets_password_and_verified_on_existing(capsys):
    c = Fake(existing={"a@b.co"})
    rc, out = run(["--email", "a@b.co", "--update", "--password", "longEnough1"], c, capsys)
    assert rc == 0 and c.updated == [("uid-a@b.co", "longEnough1")] and c.created == []


def test_update_creates_when_missing(capsys):
    c = Fake()
    rc, _ = run(["--email", "a@b.co", "--update", "--password", "longEnough1"], c, capsys)
    assert rc == 0 and c.created == [("a@b.co", "longEnough1")]


def test_weak_password_rejected(capsys):
    c = Fake()
    rc, out = run(["--email", "a@b.co", "--password", "short"], c, capsys)
    assert rc != 0
    assert "password" in out.err.lower()
    assert c.created == []
