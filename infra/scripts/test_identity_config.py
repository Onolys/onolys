"""Tests for identity-config.py logic (fake client, no network). Run: python3 -m pytest infra/scripts -q"""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("identity_config", pathlib.Path(__file__).with_name("identity-config.py"))
ic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ic)


class Fake:
    def __init__(self, cfg):
        self.cfg = cfg
        self.patches = []

    def get(self):
        return self.cfg

    def patch(self, mask, body):
        self.patches.append((mask, body))


CB = "https://app.onolys.com/auth/action"
GOOD = {
    "passwordPolicyConfig": {
        "passwordPolicyEnforcementState": "ENFORCE",
        "passwordPolicyVersions": [{"customStrengthOptions": {"minPasswordLength": 8}}],
    },
    "emailPrivacyConfig": {"enableImprovedEmailPrivacy": True},
    "notification": {"sendEmail": {"callbackUri": CB}},
}


def test_patches_when_unset():
    c = Fake({})
    ic.ensure(c)
    mask, body = c.patches[0]
    assert set(mask.split(",")) == {"passwordPolicyConfig", "emailPrivacyConfig"}
    assert c.patches[1] == ("notification.sendEmail.callbackUri", {"notification": {"sendEmail": {"callbackUri": CB}}})
    assert body["passwordPolicyConfig"]["passwordPolicyVersions"][0]["customStrengthOptions"]["minPasswordLength"] == 8
    assert body["emailPrivacyConfig"]["enableImprovedEmailPrivacy"] is True


def test_idempotent_when_already_set():
    c = Fake(GOOD)
    ic.ensure(c)
    assert c.patches == []


def test_add_domains_unions_and_skips_when_present():
    c = Fake({"authorizedDomains": ["localhost", "a.web.app"]})
    ic.add_domains(c, ["b.web.app", "a.web.app"])
    assert c.patches == [("authorizedDomains", {"authorizedDomains": ["localhost", "a.web.app", "b.web.app"]})]
    c2 = Fake({"authorizedDomains": ["a.web.app"]})
    ic.add_domains(c2, ["a.web.app"])
    assert c2.patches == []


def test_callback_uri_patched_alone_when_default_hosted_handler():
    cfg = dict(GOOD, notification={"sendEmail": {"callbackUri": "https://onolys.firebaseapp.com/__/auth/action"}})
    c = Fake(cfg)
    ic.ensure(c)
    assert c.patches == [("notification.sendEmail.callbackUri", {"notification": {"sendEmail": {"callbackUri": CB}}})]


def test_callback_uri_is_configurable():
    c = Fake(GOOD)
    ic.ensure(c, callback_uri="https://x.example/auth/action")
    assert c.patches[0][1]["notification"]["sendEmail"]["callbackUri"] == "https://x.example/auth/action"


def test_callback_failure_does_not_fail_ensure():
    class Boom(Fake):
        def patch(self, mask, body):
            if mask == "notification.sendEmail.callbackUri":
                raise SystemExit("400 EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED")
            super().patch(mask, body)

    c = Boom(dict(GOOD, notification={"sendEmail": {"callbackUri": "https://x/__/auth/action"}}))
    ic.ensure(c)
    assert c.patches == []


def test_check_passes_when_callback_matches(capsys):
    assert ic.check(Fake(GOOD)) == 0
    assert "ok" in capsys.readouterr().out


def test_check_fails_on_default_firebaseapp_url(capsys):
    cfg = dict(GOOD, notification={"sendEmail": {"callbackUri": "https://onolys.firebaseapp.com/__/auth/action"}})
    c = Fake(cfg)
    assert ic.check(c) == 1
    out = capsys.readouterr().err
    assert CB in out and "https://onolys.firebaseapp.com/__/auth/action" in out
    assert "python3 infra/scripts/identity-config.py" in out
    assert c.patches == []  # read-only


def test_check_fails_when_notification_missing():
    assert ic.check(Fake({})) == 1


def test_main_check_is_read_only_and_exits_nonzero(monkeypatch):
    c = Fake({})
    monkeypatch.setattr(ic, "Client", lambda: c)
    try:
        ic.main(["--check"])
    except SystemExit as e:
        assert e.code == 1
    else:
        raise AssertionError("expected SystemExit(1)")
    assert c.patches == []
