"""No admin infra remains (PRD 03-eval-environment R13, Decision 11). Run: python3 -m pytest infra/scripts -q"""
import re
from pathlib import Path

INFRA = Path(__file__).resolve().parents[1]
REPO = INFRA.parent
SELF = Path(__file__).resolve()
# Retired sign-in hosts must be named to be removed (identity-config.py): tests of that, and lines tagged `retired-host`.
EXEMPT = {SELF, Path(__file__).with_name("test_identity_config.py").resolve()}

# Google role names (roles/*.admin, *Admin) and the Identity Toolkit `admin/v2` REST path are allowed.
ALLOWED = [r"roles/[\w.]*admin", r"\w+_admin\b", r"\w*[Aa]dmin\b(?=[\"'`)\s]*$)", r"identitytoolkit\.googleapis\.com/admin/v2",
           r"firebaseauth\.admin", r"\.admin\b", r"(?:index|rules)Admin", r"objectAdmin", r"Hosting admin"]
FORBIDDEN = [
    "admin_enabled", "admin_site_id", "admin_staging_site_id", "admin_cors_origins", "admin_max_instances",
    "admin_backend", "admin_allowed_emails", "admin_public", "admin_emails", "web_env_admin",
    "admin-allowed-emails", "ADMIN_STAGING_", "ADMIN_AUTH", "ADMIN_ALLOWED_EMAILS", "ADMIN_CORS_ORIGINS",
    "admin.onolys.com", "onolys-admin", "admin-backend", "admin-staging",
]


def files():
    for root in (INFRA, REPO / "eval", REPO / ".firebaserc"):
        paths = [root] if root.is_file() else root.rglob("*")
        for p in paths:
            if (p.is_file() and p.resolve() not in EXEMPT and ".terraform" not in p.parts and "node_modules" not in p.parts
                    and "dist" not in p.parts and p.suffix in {".tf", ".py", ".ts", ".tsx", ".json", ".md", ".sh", ""}
                    and p.name != ".terraform.lock.hcl" and not p.name.endswith(".lock")):
                yield p


def test_no_admin_tokens_in_infra_eval_firebaserc():
    hits = []
    for p in files():
        text = "\n".join(l for l in p.read_text(errors="ignore").splitlines() if "retired-host" not in l)
        hits += [f"{p.relative_to(REPO)}: {t}" for t in FORBIDDEN if t in text]
    assert not hits, hits


def test_deleted_admin_tests_and_firebase_targets():
    for name in ("test_admin_env_wiring.py", "test_admin_enabled_per_env.py", "test_deployer_admin_iam.py"):
        assert not (INFRA / "scripts" / name).exists(), name
    fb = (REPO / ".firebaserc").read_text()
    assert "admin" not in fb.lower()
    assert re.search(r'"app":', fb) and re.search(r'"eval-staging"', fb)  # prod/staging/eval targets stay
