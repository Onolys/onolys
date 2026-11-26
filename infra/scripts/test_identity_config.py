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
    assert "EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED" in out and "custom SMTP" in out
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


# --- retiring stale authorised domains ---------------------------------------------------------------------------
LIVE = [
    "localhost", "onolys.firebaseapp.com", "onolys.web.app", "app.onolys.com", "admin.onolys.com",
    "onolys-admin.web.app", "onolys.com",
]


def test_remove_domains_drops_only_retired():
    c = Fake({"authorizedDomains": LIVE})
    ic.sync_domains(c, [], ["admin.onolys.com", "onolys-admin.web.app"])
    assert c.patches == [("authorizedDomains", {"authorizedDomains": [
        "localhost", "onolys.firebaseapp.com", "onolys.web.app", "app.onolys.com", "onolys.com"]})]


def test_remove_never_drops_firebase_defaults():
    c = Fake({"authorizedDomains": LIVE})
    ic.sync_domains(c, [], ["localhost", "onolys.firebaseapp.com", "onolys.web.app", "admin.onolys.com"])
    kept = c.patches[0][1]["authorizedDomains"]
    assert {"localhost", "onolys.firebaseapp.com", "onolys.web.app"} <= set(kept)
    assert "admin.onolys.com" not in kept


def test_remove_keeps_unmanaged_domains():
    c = Fake({"authorizedDomains": LIVE})
    ic.sync_domains(c, [], ["admin.onolys.com"])
    assert "onolys.com" in c.patches[0][1]["authorizedDomains"]


def test_add_wins_over_remove_and_add_and_remove_in_one_patch():
    c = Fake({"authorizedDomains": LIVE})
    ic.sync_domains(c, ["onolys-eval-app.web.app", "admin.onolys.com"], ["admin.onolys.com", "onolys-admin.web.app"])
    assert len(c.patches) == 1
    got = c.patches[0][1]["authorizedDomains"]
    assert "admin.onolys.com" in got and "onolys-admin.web.app" not in got and got[-1] == "onolys-eval-app.web.app"


def test_remove_noop_when_absent():
    c = Fake({"authorizedDomains": ["localhost", "a.web.app"]})
    ic.sync_domains(c, [], ["gone.web.app"])
    assert c.patches == []


def test_dry_run_reports_without_patching(capsys):
    c = Fake({"authorizedDomains": LIVE})
    ic.main_with(ic.DryRun(c), add=[], remove=["admin.onolys.com"], domains_only=True)
    assert c.patches == []
    out = capsys.readouterr().out
    assert "dry-run" in out and "admin.onolys.com" in out


def test_protected_uses_project():
    assert ic.protected_domains("onolys-staging") == {
        "localhost", "onolys-staging.firebaseapp.com", "onolys-staging.web.app"}


# --- Terraform wiring (infra/identity.tf) ------------------------------------------------------------------------
def _identity_tf():
    return (pathlib.Path(__file__).parents[1] / "identity.tf").read_text()


def test_declared_domains_keep_eval_and_prod_hosts():
    import re

    block = re.search(r"authorized_domains = distinct\(concat\((.*?)\n  \)\)\n", _identity_tf(), re.S).group(1)
    for host in ["app.onolys.com", "eval.onolys.com", "onolys-eval-staging.web.app", "onolys-eval-app.web.app", "var.app_site_id"]:
        assert host in block
    assert "admin" not in block and "app_staging_site_id" not in block


def test_retired_domains_removed_via_script():
    import re

    src = _identity_tf()
    retired = re.search(r"retired_authorized_domains = \[(.*?)\]", src, re.S).group(1)
    for host in ["admin.onolys.com", "onolys-admin.web.app", "onolys-admin-staging.web.app", "app_staging_site_id"]:
        assert host in retired
    assert "--remove-domain" in src and "local.retired_authorized_domains" in src
