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
        self.existing = set(existing)
        self.created = []
        self.verified = []

    def exists(self, email):
        return email in self.existing

    def create(self, email, password):
        self.created.append((email, password))
        return "uid-1"

    def set_verified(self, uid):
        self.verified.append(uid)


def run(args, client, capsys):
    rc = ctu.main(args, client=client)
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


def test_verified_flag_set_and_output_exact(capsys):
    c = Fake()
    rc, out = run(["--email", "a@b.co", "--password", "Sup3rSecret!"], c, capsys)
    assert rc == 0
    assert c.verified == ["uid-1"]
    assert out.out == "email: a@b.co\npassword: Sup3rSecret!\n"


def test_existing_email_errors_without_modifying(capsys):
    c = Fake(existing={"a@b.co"})
    rc, out = run(["--email", "a@b.co"], c, capsys)
    assert rc != 0
    assert "already exists" in out.err
    assert c.created == [] and c.verified == []
    assert out.out == ""


def test_custom_passthrough(capsys):
    c = Fake()
    run(["--email", "me@x.org", "--password", "longEnough1"], c, capsys)
    assert c.created == [("me@x.org", "longEnough1")]


def test_weak_password_rejected(capsys):
    c = Fake()
    rc, out = run(["--password", "short"], c, capsys)
    assert rc != 0
    assert "password" in out.err.lower()
    assert c.created == []
