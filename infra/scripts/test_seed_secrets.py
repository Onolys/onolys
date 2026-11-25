"""Tests for seed-secrets.py logic (fake client, no network). Run: python3 -m pytest infra/scripts -q"""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("seed_secrets", pathlib.Path(__file__).with_name("seed-secrets.py"))
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


class Fake:
    def __init__(self, existing=None):
        self.v = dict(existing or {})
        self.adds = []

    def latest_value(self, sid):
        return self.v.get(sid)

    def add_version(self, sid, value):
        self.v[sid] = value
        self.adds.append(sid)


def run(c, env, target="staging", **kw):
    return seed.seed(c, env=target, provider_maps={"ANTHROPIC_API_KEY": "anthropic-api-key"}, environ=env, **kw)


def test_creates_hmac_and_key_then_idempotent():
    c = Fake()
    r1 = run(c, {"ANTHROPIC_API_KEY": "sk-test-1"})
    assert r1.ok and sorted(c.adds) == ["anthropic-api-key-staging", "uid-hmac-key-staging"]
    assert len(c.v["uid-hmac-key-staging"]) >= 32
    hmac1 = c.v["uid-hmac-key-staging"]
    r2 = run(c, {"ANTHROPIC_API_KEY": "sk-test-1"})
    assert r2.ok and len(c.adds) == 2 and c.v["uid-hmac-key-staging"] == hmac1


def test_changed_value_adds_version():
    c = Fake({"uid-hmac-key-staging": b"x" * 64, "anthropic-api-key-staging": b"old"})
    run(c, {"ANTHROPIC_API_KEY": "new"})
    assert c.adds == ["anthropic-api-key-staging"] and c.v["anthropic-api-key-staging"] == b"new"


def test_missing_env_value():
    c = Fake()
    r = run(c, {})
    assert not r.ok  # no value and no existing version
    c2 = Fake({"anthropic-api-key-staging": b"old", "uid-hmac-key-staging": b"h" * 64})
    assert run(c2, {}).ok and not c2.adds  # existing version kept


def test_allowlist_only_when_requested():
    c = Fake()
    run(c, {"ANTHROPIC_API_KEY": "k", "EVAL_ALLOWED_EMAILS": "a@x.com"}, target="eval")
    assert "eval-allowed-emails-eval" not in c.v
    run(c, {"ANTHROPIC_API_KEY": "k", "EVAL_ALLOWED_EMAILS": "a@x.com"}, target="eval", allowlist=True)
    assert c.v["eval-allowed-emails-eval"] == b"a@x.com"
    assert c.v["anthropic-api-key-eval"] == b"k" and "uid-hmac-key-eval" in c.v


def test_allowlist_missing_fails_and_existing_kept():
    c = Fake()
    assert not run(c, {"ANTHROPIC_API_KEY": "k"}, target="eval", allowlist=True).ok
    c2 = Fake({"eval-allowed-emails-eval": b"keep"})
    assert run(c2, {"ANTHROPIC_API_KEY": "k"}, target="eval", allowlist=True).ok
    assert c2.v["eval-allowed-emails-eval"] == b"keep"


def test_no_admin_flag_or_env():
    src = pathlib.Path(__file__).with_name("seed-secrets.py").read_text()
    assert "ADMIN_ALLOWED_EMAILS" not in src and "--admin" not in src and "admin-allowed-emails" not in src


def test_cli_accepts_env_eval_and_allowlist(monkeypatch, capsys):
    calls = {}

    def fake_seed(client, **kw):
        calls.update(kw)
        return seed.Report()

    monkeypatch.setattr(seed, "SecretManager", lambda project: object())
    monkeypatch.setattr(seed, "seed", fake_seed)
    assert seed.main(["--env", "eval", "--allowlist"]) == 0
    assert calls["env"] == "eval" and calls["allowlist"] is True


def test_report_has_no_values():
    c = Fake()
    r = run(c, {"ANTHROPIC_API_KEY": "sk-secret-zzz"})
    assert "sk-secret-zzz" not in str(r.lines)


def test_envs_are_separate_secrets():
    c = Fake()
    run(c, {"ANTHROPIC_API_KEY": "staging-key"}, target="staging")
    run(c, {"ANTHROPIC_API_KEY": "prod-key"}, target="prod")
    assert c.v["anthropic-api-key-staging"] == b"staging-key"
    assert c.v["anthropic-api-key-prod"] == b"prod-key"
    assert "anthropic-api-key" not in c.v


def test_prod_run_does_not_touch_staging_or_legacy():
    c = Fake({"anthropic-api-key": b"legacy", "anthropic-api-key-staging": b"s"})
    run(c, {"ANTHROPIC_API_KEY": "p"}, target="prod")
    assert c.v["anthropic-api-key"] == b"legacy" and c.v["anthropic-api-key-staging"] == b"s"
    assert sorted(c.adds) == ["anthropic-api-key-prod", "uid-hmac-key-prod"]


def test_default_map_seeds_gemini_and_keeps_existing_anthropic():
    assert seed.DEFAULT_MAP == {"GEMINI_API_KEY": "gemini-api-key", "ANTHROPIC_API_KEY": "anthropic-api-key"}
    c = Fake({"anthropic-api-key-staging": b"old", "uid-hmac-key-staging": b"h" * 64})
    r = seed.seed(c, env="staging", provider_maps=seed.DEFAULT_MAP, environ={"GEMINI_API_KEY": "g-key"})
    assert r.ok and c.adds == ["gemini-api-key-staging"]  # unset ANTHROPIC_API_KEY keeps its version
    assert c.v["gemini-api-key-staging"] == b"g-key" and c.v["anthropic-api-key-staging"] == b"old"
