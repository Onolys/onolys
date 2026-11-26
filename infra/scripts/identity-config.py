#!/usr/bin/env python3
"""Identity Platform settings the Terraform google provider cannot express (PRD R4), plus extra authorised domains.

Usage (ADC, quota project `onolys`):
  python3 infra/scripts/identity-config.py                      # ensure password policy (min 8) + enumeration protection + email action URL
  python3 infra/scripts/identity-config.py --check              # read-only drift check of the email action URL (exit 1 on drift)
  python3 infra/scripts/identity-config.py --domains-only --add-domain HOST ...  # union HOST(s) into authorised domains
  python3 infra/scripts/identity-config.py --domains-only --remove-domain HOST ...  # retire HOST(s) (explicit list only)
  add --dry-run to any mode to print the PATCHes instead of sending them

Idempotent: PATCHes only when the live config differs. Domains are removed ONLY when named with --remove-domain
(Terraform passes its explicit "retired" list); Firebase's defaults (localhost, <project>.firebaseapp.com,
<project>.web.app) are never removed, a host that is also added is kept, and anything else (preview channel hosts,
console-added domains) is left alone.
Terraform runs it (with the base domain list) when this file or the lists change
(terraform_data.identity_policy). Preview channel hosts are added by the SP00 preview workflow with
--domains-only: the wildcard `onolys-app-staging--pr-*.web.app` is rejected by the API
(INVALID_AUTHORIZED_DOMAIN), see docs/reference/testing.md "Preview auth domains".
"""
import argparse
import json
import sys
import urllib.request

PROJECT = "onolys"
BASE = f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PROJECT}/config"

POLICY = {
    "passwordPolicyEnforcementState": "ENFORCE",
    "passwordPolicyVersions": [{"customStrengthOptions": {"minPasswordLength": 8}}],
}
PRIVACY = {"enableImprovedEmailPrivacy": True}
# Email links (verify email, reset password) go to our in-app handler: Google's hosted one calls the API
# with the config's `AQ.` key and fails with 401 (shown as "link expired").
DEFAULT_CALLBACK_URI = "https://app.onolys.com/auth/action"
CALLBACK_MASK = "notification.sendEmail.callbackUri"


def _policy_ok(cur):
    vers = (cur or {}).get("passwordPolicyVersions") or []
    return (
        (cur or {}).get("passwordPolicyEnforcementState") == "ENFORCE"
        and any(v.get("customStrengthOptions", {}).get("minPasswordLength") == 8 for v in vers)
    )


def ensure(client, callback_uri=DEFAULT_CALLBACK_URI):
    cfg = client.get()
    body = {}
    masks = []
    if not _policy_ok(cfg.get("passwordPolicyConfig")):
        body["passwordPolicyConfig"] = POLICY
        masks.append("passwordPolicyConfig")
    if not (cfg.get("emailPrivacyConfig") or {}).get("enableImprovedEmailPrivacy"):
        body["emailPrivacyConfig"] = PRIVACY
        masks.append("emailPrivacyConfig")
    if body:
        client.patch(",".join(masks), body)
        print("patched: " + ", ".join(masks))
    else:
        print("already set")
    if ((cfg.get("notification") or {}).get("sendEmail") or {}).get("callbackUri") != callback_uri:
        # Best effort: the API answers 400 EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED when email method is DEFAULT
        # (callbackUri is immutable then); do not fail the policy/privacy settings above because of it.
        try:
            client.patch(CALLBACK_MASK, {"notification": {"sendEmail": {"callbackUri": callback_uri}}})
            print("patched: " + CALLBACK_MASK)
        except SystemExit as e:
            print(f"warning: callbackUri not updated (immutable with default email method): {str(e)[:120]}")


def check(client, callback_uri=DEFAULT_CALLBACK_URI):
    """Read-only drift check: 0 if the live email action URL is ours, else 1 with the remedy on stderr."""
    actual = ((client.get().get("notification") or {}).get("sendEmail") or {}).get("callbackUri")
    if actual == callback_uri:
        print(f"ok: {CALLBACK_MASK} = {actual}")
        return 0
    print(
        f"DRIFT: {CALLBACK_MASK} expected {callback_uri} but live is {actual!r}; verify/reset links will show "
        "'expired or already used'. Fix: python3 infra/scripts/identity-config.py (if it warns the template is immutable "
        "(EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED, sender method DEFAULT), switch the Firebase Auth email sender to custom SMTP first)",
        file=sys.stderr,
    )
    return 1


def protected_domains(project=PROJECT):
    """Firebase's project defaults: never removed, whatever the retired list says."""
    return {"localhost", f"{project}.firebaseapp.com", f"{project}.web.app"}


def sync_domains(client, add, remove=(), project=PROJECT):
    """Union `add` into the authorised domains and drop the explicitly retired `remove` hosts in one PATCH."""
    cur = client.get().get("authorizedDomains", [])
    keep_always = protected_domains(project) | set(add)
    gone = [h for h in cur if h in set(remove) and h not in keep_always]
    new = [h for h in add if h not in cur]
    if not new and not gone:
        print("domains already in sync")
        return
    client.patch("authorizedDomains", {"authorizedDomains": [h for h in cur if h not in gone] + new})
    if new:
        print("added: " + ", ".join(new))
    if gone:
        print("removed: " + ", ".join(gone))


def add_domains(client, hosts):
    sync_domains(client, hosts, ())


class DryRun:
    """Wraps a client: reads pass through, PATCHes are printed instead of sent."""

    def __init__(self, inner):
        self.inner = inner

    def get(self):
        return self.inner.get()

    def patch(self, mask, body):
        print(f"dry-run: would PATCH updateMask={mask} body={json.dumps(body)}")


class Client:
    def __init__(self):
        import google.auth
        import google.auth.transport.requests as tr

        self.creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self.tr = tr.Request()

    def _call(self, method, url, body=None):
        self.creds.refresh(self.tr)
        req = urllib.request.Request(
            url,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.creds.token}",
                "x-goog-user-project": PROJECT,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            sys.exit(f"{method} {url} -> {e.code}: {e.read().decode()[:500]}")

    def get(self):
        return self._call("GET", BASE)

    def patch(self, mask, body):
        self._call("PATCH", f"{BASE}?updateMask={mask}", body)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--add-domain", action="append", default=[], metavar="HOST")
    ap.add_argument("--remove-domain", action="append", default=[], metavar="HOST", help="retire HOST from authorised domains (never Firebase defaults)")
    ap.add_argument("--dry-run", action="store_true", help="print the PATCHes instead of sending them")
    ap.add_argument("--callback-uri", default=DEFAULT_CALLBACK_URI, metavar="URL", help="email action URL (verify/reset links)")
    ap.add_argument("--domains-only", action="store_true", help="skip the policy check (fast path for CI preview deploys)")
    ap.add_argument("--check", action="store_true", help="read-only: exit 1 if the live callbackUri differs from the expected URL")
    args = ap.parse_args(argv)
    c = Client()
    if args.dry_run:
        c = DryRun(c)
    if args.check:
        sys.exit(check(c, args.callback_uri))
    main_with(c, args.add_domain, args.remove_domain, args.domains_only, args.callback_uri)


def main_with(c, add=(), remove=(), domains_only=False, callback_uri=DEFAULT_CALLBACK_URI):
    if not domains_only:
        ensure(c, callback_uri)
    if add or remove:
        sync_domains(c, list(add), list(remove))


if __name__ == "__main__":
    main()
