#!/usr/bin/env python3
"""Create (or update) a pre-verified Firebase Auth email/password user in a NON-PROD project.

Eval has no sign-up and sends no email: the operator runs this script to create accounts directly in the
project's Identity Platform with emailVerified=true (the API/eval backend reject unverified emails). It uses the
Identity Toolkit management API with ADC and the target project as quota project. The prod project `onolys` is
refused. Default project: onolys-eval.

Usage:
  python3 infra/scripts/create-test-user.py --email a@b.co                 # password from $ONOLYS_ACCOUNT_PASSWORD, else prompted (no echo)
  ONOLYS_ACCOUNT_PASSWORD=... python3 infra/scripts/create-test-user.py --email a@b.co
  python3 infra/scripts/create-test-user.py --email a@b.co --generate      # generated password, printed once
  python3 infra/scripts/create-test-user.py --email a@b.co --update        # existing user: set password, mark verified
  python3 infra/scripts/create-test-user.py [--project onolys-eval]        # no --email: random test-onolys-<hex>@onolys.com + generated password

`--password` still works but exposes the value in shell history/process list; prefer the env var or prompt.
Without --update an existing email exits non-zero and is not modified. Add eval users' emails to the eval allowlist
(secret eval-allowed-emails-eval) separately.
"""
import argparse
import getpass
import json
import os
import secrets
import string
import sys
import urllib.request

DEFAULT_PROJECT = "onolys-eval"
PROD_PROJECTS = {"onolys", "onolys-prod", "1054076260967"}  # id, name and display name of prod
PASSWORD_ENV = "ONOLYS_ACCOUNT_PASSWORD"
MIN_LEN = 8  # identity-config.py POLICY minPasswordLength
SYMBOLS = "!@#$%^&*-_"


def project_errors(project):
    if project.strip().lower() in PROD_PROJECTS:
        return [f"refusing to touch production project {project!r}; use a non-prod project such as {DEFAULT_PROJECT}"]
    return []


def create_payload(email, password):
    return {"email": email, "password": password, "emailVerified": True}


def update_payload(uid, password):
    return {"localId": uid, "password": password, "emailVerified": True}


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


def prompt_password():
    first = getpass.getpass("Password: ")
    if getpass.getpass("Repeat password: ") != first:
        sys.exit("error: passwords differ")
    return first


class Client:
    def __init__(self, project=DEFAULT_PROJECT):
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

    def lookup(self, email):
        users = self._call(f"{self.base}:lookup", {"email": [email]}).get("users")
        return users[0]["localId"] if users else None

    def create(self, email, password):
        return self._call(self.base, create_payload(email, password))["localId"]

    def update(self, uid, password):
        self._call(f"{self.base}:update", update_payload(uid, password))


def main(argv=None, client=None, env=None, prompt=prompt_password):
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", help="default: test-onolys-<8 hex>@onolys.com")
    ap.add_argument("--password", help="discouraged (visible in process list); prefer $" + PASSWORD_ENV + " or the prompt")
    ap.add_argument("--generate", action="store_true", help="generate a strong password and print it")
    ap.add_argument("--update", action="store_true", help="if the user exists, set its password and mark it verified")
    ap.add_argument("--project", default=DEFAULT_PROJECT)
    args = ap.parse_args(argv)
    errs = project_errors(args.project)
    if errs:
        print("error: " + "; ".join(errs), file=sys.stderr)
        return 2
    email = args.email or generate_email()
    generated = False
    if args.password:
        password = args.password
    elif env.get(PASSWORD_ENV):
        password = env[PASSWORD_ENV]
    elif args.generate or not args.email:
        password, generated = generate_password(), True
    else:
        password = prompt()
    errs = password_errors(password)
    if errs:
        print("error: password " + "; ".join(errs), file=sys.stderr)
        return 2
    c = client or Client(args.project)
    uid = c.lookup(email)
    if uid and not args.update:
        print(f"error: user {email} already exists; not modified (use --update to reset its password)", file=sys.stderr)
        return 1
    if uid:
        c.update(uid, password)
    else:
        c.create(email, password)
    print(f"email: {email}\nproject: {args.project}" + (f"\npassword: {password}" if generated else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
