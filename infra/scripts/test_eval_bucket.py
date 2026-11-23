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
