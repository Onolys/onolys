"""The evaluation data bucket exists only in staging and cannot be public."""
import re
from pathlib import Path


def test_private_staging_only_eval_bucket():
    root = Path(__file__).resolve().parents[1]
    text = (root / 'eval.tf').read_text()
    assert 'resource "google_storage_bucket" "eval_staging"' in text
    for pattern in [r'name\s*=\s*"onolys-eval-data-staging"',
                    r'uniform_bucket_level_access\s*=\s*true',
                    r'public_access_prevention\s*=\s*"enforced"',
                    r'versioning\s*\{\s*enabled\s*=\s*false',
                    r'force_destroy\s*=\s*false']:
        assert re.search(pattern, text)
    assert 'google_storage_bucket_iam' not in text
    assert 'eval' not in (root / 'modules/environment/main.tf').read_text()


def test_browser_put_cors_allows_eval_and_local_origins_and_signed_headers():
    root = Path(__file__).resolve().parents[1]
    text = (root / 'eval.tf').read_text()
    cors = re.search(r'cors\s*\{([^}]+)\}', text)
    assert cors is not None
    block = cors.group(1)
    for origin in ['https://onolys-eval-staging.web.app', 'https://eval.onolys.com',
                   'http://localhost:5173', 'http://127.0.0.1:5173']:
        assert f'"{origin}"' in block
    assert re.search(r'method\s*=\s*\["PUT"\]', block)
    for header in ['Content-Type', 'x-goog-content-length-range', 'x-goog-if-generation-match']:
        assert f'"{header}"' in block
    assert '"*"' not in block
