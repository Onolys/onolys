#!/usr/bin/env python3
"""Create a pre-verified Firebase Auth email/password user for PR previews / staging.

The API rejects unverified emails (api/src/onolys_api/auth/idtoken.py), so a normal signup cannot sign in
until the verify link is clicked. This creates the user with emailVerified=true via the Identity Toolkit
management API (ADC, quota project `onolys`, same auth as identity-config.py).

Usage:
  python3 infra/scripts/create-test-user.py [--email EMAIL] [--password PASSWORD] [--project onolys]

Prints `email: ...` and `password: ...`. Exits non-zero if the email already exists (user is not modified).
The user pool is shared by staging and prod: delete test users in the Firebase console when done.
"""
import argparse
import json
import secrets
import string
import sys
import urllib.request

PROJECT = "onolys"
MIN_LEN = 8  # identity-config.py POLICY minPasswordLength
SYMBOLS = "!@#$%^&*-_"


def password_errors(pw):
    errs = []
    if len(pw) < MIN_LEN:
        errs.append(f"must be at least {MIN_LEN} characters")
    return errs


def generate_password():
    """>= 16 chars with upper, lower, digit and symbol (satisfies any strength option)."""
    while True:
        pw = secrets.token_urlsafe(18)  # 24 chars
        if any(c.isupper() for c in pw) and any(c.islower() for c in pw) and any(c.isdigit() for c in pw):
            return pw[:-1] + secrets.choice(SYMBOLS)


def generate_email():
    return f"test-onolys-{secrets.token_hex(4)}@onolys.com"


class Client:
    def __init__(self, project=PROJECT):
        import google.auth
        import google.auth.transport.requests as tr

        self.project = project
        self.base = f"https://identitytoolkit.googleapis.com/v1/projects/{project}/accounts"
        self.creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self.tr = tr.Request()

    def _call(self, url, body):
        self.creds.refresh(self.tr)
        req = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self.creds.token}",
                "x-goog-user-project": self.project,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            sys.exit(f"POST {url} -> {e.code}: {e.read().decode()[:500]}")

    def exists(self, email):
        return bool(self._call(f"{self.base}:lookup", {"email": [email]}).get("users"))

    def create(self, email, password):
        return self._call(self.base, {"email": email, "password": password})["localId"]

    def set_verified(self, uid):
        self._call(f"{self.base}:update", {"localId": uid, "emailVerified": True})


def main(argv=None, client=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", help="default: test-onolys-<8 hex>@onolys.com")
    ap.add_argument("--password", help=f"default: generated; min {MIN_LEN} chars")
    ap.add_argument("--project", default=PROJECT)
    args = ap.parse_args(argv)
    email = args.email or generate_email()
    password = args.password or generate_password()
    errs = password_errors(password)
    if errs:
        print("error: password " + "; ".join(errs), file=sys.stderr)
        return 2
    c = client or Client(args.project)
    if c.exists(email):
        print(f"error: user {email} already exists; not modified", file=sys.stderr)
        return 1
    c.set_verified(c.create(email, password))
    print(f"email: {email}\npassword: {password}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
