"""Isolation boundaries for the opt-in project root and legacy module defaults."""
import re
from pathlib import Path

INFRA = Path(__file__).resolve().parents[1]
ROOT = INFRA / 'isolated-environment'
MODULE = INFRA / 'modules/environment'


def block(text, kind, name):
    found = re.search(rf'{kind} "{name}" \{{(.*?)\n\}}', text, re.DOTALL)
    assert found, name
    return found[1]


def test_optional_module_inputs_preserve_legacy_names_and_identity():
    variables = (MODULE / 'variables.tf').read_text()
    for key in ['audio_bucket_name', 'auth_project', 'speech_object_prefix']:
        assert re.search(r'default\s*=\s*null', block(variables, 'variable', key))
    assert 'coalesce(var.audio_bucket_name, "onolys-audio-${var.env}")' in (MODULE / 'main.tf').read_text()
    for filename in ['services.tf', 'voice.tf']:
        assert 'coalesce(var.auth_project, var.project)' in (MODULE / filename).read_text()


def test_new_root_is_separate_and_refuses_production_or_state_reuse():
    versions = (ROOT / 'versions.tf').read_text()
    main = (ROOT / 'main.tf').read_text()
    assert 'backend "gcs" {}' in versions
    assert 'onolys-tfstate' not in versions
    assert 'source' in main and '../modules/environment' in main
    assert 'triggers_replace = [var.project, var.environment]' in main
    assert 'prevent_destroy = true' in main
    assert 'var.project == "onolys-${var.environment}"' in (ROOT / 'variables.tf').read_text()
    for env in ['staging', 'eval']:
        backend = (ROOT / 'examples' / f'backend-{env}.hcl.example').read_text()
        assert f'bucket = "onolys-{env}-tfstate"' in backend
        assert 'prefix = "environment"' in backend
        example = (ROOT / 'examples' / f'environment-{env}.tfvars.example').read_text()
        assert 'project' in example and f'"onolys-{env}"' in example


def test_deployer_and_cross_project_image_readers_are_scoped():
    deployer = (ROOT / 'deployer.tf').read_text()
    assert "assertion.repository=='${var.github_repository}'" in deployer
    assert "assertion.ref=='refs/heads/main'" in deployer
    assert 'resource "google_artifact_registry_repository_iam_member" "reader"' in deployer
    assert 'for_each' in deployer and 'var.artifact_registry_reader_members' in deployer
    assert 'roles/artifactregistry.reader' in deployer
    assert 'google_project_iam_binding' not in deployer
    assert 'projects/onolys/' not in deployer and '1054076260967' not in deployer


def test_eval_speech_prefix_and_optional_readers_preserve_isolation():
    root = (ROOT / 'main.tf').read_text()
    assert '"eval-uploads/"' in root and 'speech_object_prefix' in root
    module = (MODULE / 'main.tf').read_text()
    assert 'var.speech_object_prefix != null' in module
    deployer = (ROOT / 'deployer.tf').read_text()
    assert 'roles/run.viewer' in deployer and 'var.cloud_run_reader_members' in deployer
    assert 'generativelanguage.googleapis.com' in root
    assert 'var.environment == "staging" ? ["aiplatform.googleapis.com"] : []' in root
    assert 'cloudfunctions.googleapis.com' not in root
