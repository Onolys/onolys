"""Eval hosting: authorized domains + web config outputs (PRD 03-eval-environment R10a-b, Decision 18)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def tf(name):
    return (ROOT / name).read_text()


def block(src, header):
    start = src.index(header)
    return src[start:src.index("\n}\n", start)]


def test_authorized_domains_include_eval_unconditionally():
    locals_src = block(tf("identity.tf"), "authorized_domains = distinct(")
    assert "eval.onolys.com" in locals_src
    assert "onolys-eval-staging.web.app" in locals_src
    assert "eval_enabled" not in locals_src
    assert not re.search(r"\?\s*\[[^\]]*eval", locals_src)


def test_no_separate_eval_firebase_web_app():
    all_tf = "\n".join(p.read_text() for p in ROOT.glob("*.tf"))
    assert 'google_firebase_web_app" "eval' not in all_tf


def test_web_env_eval_output_uses_prod_values_and_eval_auth_domain():
    out = block(tf("identity.tf"), 'output "web_env_eval"')
    assert "google_firebase_web_app.app.app_id" in out
    assert "data.google_firebase_web_app_config.app.api_key" in out
    assert '"eval.onolys.com"' in out
    assert "VITE_FIREBASE_AUTH_DOMAIN" in out
