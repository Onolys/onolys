#!/usr/bin/env python3
"""Offline regression checks for isolated release targets and legacy fallback."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


class TargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('release_target', ROOT / 'scripts/ci/release_target.py')
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_project_is_activation_switch(self):
        self.module.validate('staging', {})
        self.module.validate('staging', {'STAGING_WIF_PROVIDER': 'prepared'})
        # Eval has no legacy target any more (its legacy site and prod sign-in were removed): always isolated.
        for env in ({}, {'EVAL_WIF_PROVIDER': 'prepared'}):
            with self.assertRaises(ValueError):
                self.module.validate('eval', env)
        with self.assertRaises(ValueError) as ctx:
            self.module.validate('eval', {'EVAL_GCP_PROJECT': 'onolys'})
        self.assertNotIn('legacy', str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            self.module.validate('staging', {'STAGING_GCP_PROJECT': 'onolys'})
        self.assertIn('clear it to use the legacy target', str(ctx.exception))

    def test_active_bundle_requires_project_local_identity_and_site(self):
        for role in ('staging', 'eval'):
            prefix = role.upper()
            values = {f'{prefix}_GCP_PROJECT': f'onolys-{role}',
                      f'{prefix}_WIF_PROVIDER': 'projects/123/locations/global/workloadIdentityPools/github/providers/github',
                      f'{prefix}_DEPLOYER_SA': f'deployer-{role}@onolys-{role}.iam.gserviceaccount.com',
                      f'{prefix}_HOSTING_SITE': ('onolys-staging-app' if role == 'staging' else 'onolys-eval-app')}
            if role == 'staging':
                values.update(STAGING_ISOLATED_VITE_FIREBASE_API_KEY='test-api-key',
                              STAGING_ISOLATED_VITE_FIREBASE_AUTH_DOMAIN='onolys-staging.firebaseapp.com',
                              STAGING_ISOLATED_VITE_FIREBASE_APP_ID='1:123:web:abc',
                              STAGING_ISOLATED_VITE_FIREBASE_STORAGE_BUCKET='onolys-staging.firebasestorage.app',
                              STAGING_ISOLATED_VITE_FIREBASE_MESSAGING_SENDER_ID='123')
            else:
                values.update(EVAL_VITE_FIREBASE_API_KEY='test-api-key',
                              EVAL_VITE_FIREBASE_AUTH_DOMAIN='onolys-eval.firebaseapp.com',
                              EVAL_VITE_FIREBASE_APP_ID='1:123:web:abc')
            self.module.validate(role, values)
            for field in ('WIF_PROVIDER', 'DEPLOYER_SA', 'HOSTING_SITE'):
                with self.subTest(role=role, missing=field), self.assertRaises(ValueError):
                    self.module.validate(role, {**values, f'{prefix}_{field}': ''})
            for field, bad in [('GCP_PROJECT', 'onolys'), ('DEPLOYER_SA', 'deployer@onolys.iam.gserviceaccount.com'),
                               ('WIF_PROVIDER', '$(evil)'), ('HOSTING_SITE', 'onolys-app'),
                               ('HOSTING_SITE', 'onolys-eval-staging'), ('HOSTING_SITE', 'x\nEVIL=1')]:
                with self.subTest(role=role, invalid=field), self.assertRaises(ValueError):
                    self.module.validate(role, {**values, f'{prefix}_{field}': bad})

    def test_eval_frontend_bundle_uses_its_own_firebase_app(self):
        base = {'EVAL_GCP_PROJECT': 'onolys-eval',
                'EVAL_WIF_PROVIDER': 'projects/123/locations/global/workloadIdentityPools/github/providers/github',
                'EVAL_DEPLOYER_SA': 'deployer-eval@onolys-eval.iam.gserviceaccount.com',
                'EVAL_HOSTING_SITE': 'onolys-eval-app',
                'EVAL_VITE_FIREBASE_API_KEY': 'k',
                'EVAL_VITE_FIREBASE_AUTH_DOMAIN': 'onolys-eval.firebaseapp.com',
                'EVAL_VITE_FIREBASE_APP_ID': '1:123:web:abc'}
        self.module.validate('eval', base)
        for field in ('API_KEY', 'AUTH_DOMAIN', 'APP_ID'):
            with self.subTest(missing=field), self.assertRaises(ValueError):
                self.module.validate('eval', {**base, f'EVAL_VITE_FIREBASE_{field}': ''})
        for field, bad in [('AUTH_DOMAIN', 'eval.onolys.com'), ('AUTH_DOMAIN', 'onolys.firebaseapp.com'),
                           ('APP_ID', 'not-an-app-id')]:
            with self.subTest(invalid=field, value=bad), self.assertRaises(ValueError):
                self.module.validate('eval', {**base, f'EVAL_VITE_FIREBASE_{field}': bad})

    def test_staging_frontend_bundle_is_required_only_after_activation(self):
        env = {'STAGING_GCP_PROJECT': 'onolys-staging',
               'STAGING_WIF_PROVIDER': 'projects/123/locations/global/workloadIdentityPools/github/providers/github',
               'STAGING_DEPLOYER_SA': 'deployer-staging@onolys-staging.iam.gserviceaccount.com',
               'STAGING_HOSTING_SITE': 'onolys-staging-app'}
        with self.assertRaises(ValueError):
            self.module.validate('staging', env)
        # Legacy build vars are never consumed by isolated staging.
        with self.assertRaises(ValueError):
            self.module.validate('staging', {**env, 'STAGING_VITE_FIREBASE_API_KEY': 'legacy'})

    def test_isolated_voice_csp_changes_only_staging(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp, 'firebase.json')
            config.write_text((ROOT / 'web/firebase.json').read_text())
            before = json.loads(config.read_text())
            self.module.configure_voice(config, 'https://onolys-voice-staging-123.us-central1.run.app')
            after = json.loads(config.read_text())
            self.assertEqual(before['hosting'][0], after['hosting'][0])
            self.assertIn('wss://onolys-voice-staging-123.us-central1.run.app', str(after['hosting'][1]))
            self.assertNotIn('1054076260967', str(after['hosting'][1]))
            with self.assertRaises(ValueError):
                self.module.configure_voice(config, 'https://evil.example/path')

    def test_voice_origin_accepts_the_service_env_wss_form(self):
        # The api service env VOICE_URL is wss://<host>.run.app (api/config.py); the CSP origin is the same host.
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp, 'firebase.json')
            config.write_text((ROOT / 'web/firebase.json').read_text())
            self.module.configure_voice(config, 'wss://onolys-voice-staging-123.us-central1.run.app')
            after = json.loads(config.read_text())
            self.assertIn('wss://onolys-voice-staging-123.us-central1.run.app', str(after['hosting'][1]))
            for bad in ('ws://onolys-voice-staging-123.us-central1.run.app', 'wss://evil.example', 'wss://x.run.app/path'):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    self.module.configure_voice(config, bad)

    def test_hosting_mapping_is_project_scoped(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp, 'firebase.json')
            config.write_text(json.dumps({'hosting': [{'target': 'app-staging'}]}))
            rc = Path(temp, '.firebaserc')
            legacy = {'projects': {'default': 'onolys'}, 'targets': {'onolys': {'hosting': {'app': ['onolys-app']}}}}
            rc.write_text(json.dumps(legacy))
            self.module.configure_hosting(config, 'onolys-staging', 'app-staging', 'onolys-staging-isolated')
            actual = json.loads(rc.read_text())
            self.assertEqual(actual['targets']['onolys'], legacy['targets']['onolys'])
            self.assertEqual(actual['targets']['onolys-staging']['hosting'], {'app-staging': ['onolys-staging-isolated']})
            with self.assertRaises(ValueError):
                self.module.configure_hosting(config, 'onolys-staging', 'missing', 'onolys-staging-isolated')


    PREVIEW_ENV = {
        'STAGING_GCP_PROJECT': 'onolys-staging',
        'STAGING_PREVIEW_WIF_PROVIDER': 'projects/123/locations/global/workloadIdentityPools/github-pr/providers/github-pr',
        'STAGING_PREVIEW_SA': 'pr-preview-staging@onolys-staging.iam.gserviceaccount.com',
        'STAGING_HOSTING_SITE': 'onolys-staging-app',
        'STAGING_ISOLATED_VITE_FIREBASE_API_KEY': 'k',
        'STAGING_ISOLATED_VITE_FIREBASE_AUTH_DOMAIN': 'onolys-staging.firebaseapp.com',
        'STAGING_ISOLATED_VITE_FIREBASE_APP_ID': '1:123:web:abc',
    }

    def test_isolated_preview_requires_its_own_limited_identity(self):
        self.module.validate_preview({})
        self.module.validate_preview({'STAGING_GCP_PROJECT': ''})
        self.module.validate_preview(self.PREVIEW_ENV)
        no_web = {k: v for k, v in self.PREVIEW_ENV.items() if 'ISOLATED' not in k}
        self.module.validate_preview(no_web, web=False)
        with self.assertRaises(ValueError):
            self.module.validate_preview(no_web)
        for field in ('STAGING_PREVIEW_WIF_PROVIDER', 'STAGING_PREVIEW_SA', 'STAGING_HOSTING_SITE'):
            with self.subTest(missing=field), self.assertRaises(ValueError):
                self.module.validate_preview({**self.PREVIEW_ENV, field: ''})
        for field, bad in [
            ('STAGING_GCP_PROJECT', 'onolys'),
            ('STAGING_PREVIEW_WIF_PROVIDER', 'projects/123/locations/global/workloadIdentityPools/github/providers/github'),
            # Same provider id in the deployer pool: previews must use the separate preview pool.
            ('STAGING_PREVIEW_WIF_PROVIDER', 'projects/123/locations/global/workloadIdentityPools/github/providers/github-pr'),
            ('STAGING_PREVIEW_WIF_PROVIDER', 'projects/123/locations/global/workloadIdentityPools/github-pr/providers/github'),
            ('STAGING_PREVIEW_SA', 'deployer-staging@onolys-staging.iam.gserviceaccount.com'),
            ('STAGING_PREVIEW_SA', 'pr-preview-staging@onolys.iam.gserviceaccount.com'),
            ('STAGING_HOSTING_SITE', 'onolys-app-staging'),
        ]:
            with self.subTest(invalid=field, value=bad), self.assertRaises(ValueError):
                self.module.validate_preview({**self.PREVIEW_ENV, field: bad}, web=False)


class WorkflowTests(unittest.TestCase):
    def workflow(self, name):
        return yaml.safe_load((ROOT / '.github/workflows' / name).read_text())

    def test_workflows_guard_active_targets_before_auth(self):
        for filename, job, role in [('deploy-staging.yml', 'build', 'staging'), ('deploy-eval.yml', 'build', 'eval'),
                                    ('deploy-prod.yml', 'resolve', 'staging')]:
            workflow = self.workflow(filename)
            steps = workflow['jobs'][job]['steps']
            guard = next(i for i, step in enumerate(steps) if f'release_target.py {role}' in step.get('run', ''))
            auth = next(i for i, step in enumerate(steps) if step.get('uses', '').startswith('google-github-actions/auth@'))
            self.assertLess(guard, auth, filename)
            for field in ('GCP_PROJECT', 'WIF_PROVIDER', 'DEPLOYER_SA', 'HOSTING_SITE'):
                self.assertIn(f'{role.upper()}_{field}', steps[guard]['env'])
            self.assertNotIn('${{', steps[guard]['run'])

    def test_staging_target_reaches_all_cloud_writes(self):
        workflow = self.workflow('deploy-staging.yml')
        for job in ('deploy-api', 'deploy-worker', 'deploy-voice'):
            inputs = workflow['jobs'][job]['with']
            self.assertIn('vars.STAGING_GCP_PROJECT', inputs['project'])
            self.assertIn('vars.STAGING_GCP_PROJECT && vars.STAGING_WIF_PROVIDER', inputs['workload_identity_provider'])
            self.assertIn('vars.STAGING_GCP_PROJECT && vars.STAGING_DEPLOYER_SA', inputs['service_account'])
        api_env = workflow['jobs']['deploy-api']['with']['env_vars']
        self.assertIn('STAGING_HOSTING_SITE', api_env)
        self.assertIn('STAGING_HOSTING_SITE', workflow['env']['STAGING_SITE'])
        web = str(workflow['jobs']['web'])
        self.assertIn('release_target.py hosting web/firebase.json', web)
        self.assertIn('hosting:app-staging', web)
        frontend = next(step for step in workflow['jobs']['web']['steps'] if step.get('working-directory') == 'web')
        self.assertEqual(frontend['env']['VITE_APP_HOSTS'], "${{ vars.STAGING_GCP_PROJECT && 'onolys-staging-app.web.app' || '' }}")
        steps = workflow['jobs']['web']['steps']
        setup = next(i for i, step in enumerate(steps) if step.get('uses', '').startswith('google-github-actions/setup-gcloud@'))
        voice = next(i for i, step in enumerate(steps) if 'release_target.py voice' in step.get('run', ''))
        auth = next(i for i, step in enumerate(steps) if step.get('uses', '').startswith('google-github-actions/auth@'))
        self.assertLess(auth, setup)
        self.assertLess(setup, voice)
        self.assertEqual(steps[setup]['if'], "vars.STAGING_GCP_PROJECT != ''")

    def test_eval_uses_its_own_project_deployer_and_firebase_app(self):
        workflow = self.workflow('deploy-eval.yml')
        text = (ROOT / '.github/workflows/deploy-eval.yml').read_text()
        self.assertEqual(workflow['env']['PROJECT'], '${{ vars.EVAL_GCP_PROJECT }}')
        self.assertEqual(workflow['env']['EVAL_SITE'], '${{ vars.EVAL_HOSTING_SITE }}')
        for forbidden in ('PROD_VITE_', 'vars.GCP_PROJECT', 'vars.WIF_PROVIDER', 'vars.DEPLOYER_STAGING_SA',
                          'FIREBASE_AUTH_DOMAIN: eval.onolys.com'):
            self.assertNotIn(forbidden, text)
        site = workflow['jobs']['site']
        frontend = next(step for step in site['steps'] if step.get('working-directory') == 'eval/web')
        self.assertEqual(frontend['env']['VITE_FIREBASE_PROJECT_ID'], '${{ env.PROJECT }}')
        for key in ('API_KEY', 'AUTH_DOMAIN', 'APP_ID'):
            self.assertEqual(frontend['env'][f'VITE_FIREBASE_{key}'], '${{ vars.EVAL_VITE_FIREBASE_' + key + ' }}')
        for name in ('build', 'deploy-backend', 'site', 'firestore'):
            auth = next(step for step in workflow['jobs'][name]['steps'] if step.get('uses', '').startswith('google-github-actions/auth@'))
            self.assertEqual(auth['with']['service_account'], '${{ vars.EVAL_DEPLOYER_SA }}')
        worker = workflow['jobs']['deploy-worker']['with']
        self.assertEqual(worker['project'], '${{ vars.EVAL_GCP_PROJECT }}')
        self.assertEqual(worker['service_account'], '${{ vars.EVAL_DEPLOYER_SA }}')
        self.assertIn('release_target.py hosting eval/web/firebase.json', str(site))
        smoke = str(workflow['jobs']['smoke'])
        self.assertIn('$EVAL_SITE.web.app', smoke)

    def test_production_reads_staging_and_writes_legacy_project(self):
        workflow = self.workflow('deploy-prod.yml')
        resolve = workflow['jobs']['resolve']
        self.assertIn('vars.STAGING_GCP_PROJECT', resolve['env']['PROJECT'])
        auth = next(step for step in resolve['steps'] if step.get('uses', '').startswith('google-github-actions/auth@'))
        self.assertEqual(auth['with']['service_account'], '${{ vars.DEPLOYER_STAGING_SA }}')
        self.assertEqual(auth['with']['workload_identity_provider'], '${{ vars.WIF_PROVIDER }}')
        self.assertEqual(workflow['env']['PROJECT'], "${{ vars.GCP_PROJECT || 'onolys' }}")
        for name in ('deploy-api', 'deploy-worker', 'deploy-voice'):
            job = workflow['jobs'][name]
            self.assertEqual(job['needs'], 'resolve')
            self.assertEqual(job['with']['project'], "${{ vars.GCP_PROJECT || 'onolys' }}")
            self.assertNotIn('service_account', job['with'])
        self.assertNotIn('environment', resolve)
        self.assertIn('PROD_LLM_PROVIDER', str(resolve))

    def test_previews_run_on_isolated_staging_with_the_preview_identity(self):
        for name, job in [('pr-preview.yml', 'preview'), ('pr-preview-cleanup.yml', 'cleanup')]:
            workflow = self.workflow(name)
            guard = workflow['jobs'][job]['if']
            self.assertNotIn('STAGING_GCP_PROJECT', guard)
            self.assertIn('head.repo.full_name == github.repository', guard)
            steps = workflow['jobs'][job]['steps']
            check = next(i for i, step in enumerate(steps) if 'release_target.py preview' in step.get('run', ''))
            auth = next(i for i, step in enumerate(steps) if step.get('uses', '').startswith('google-github-actions/auth@'))
            self.assertLess(check, auth, name)
            self.assertNotIn('${{', steps[check]['run'])
            for field in ('GCP_PROJECT', 'PREVIEW_WIF_PROVIDER', 'PREVIEW_SA', 'HOSTING_SITE'):
                self.assertIn(f'STAGING_{field}', steps[check]['env'])
            with_ = steps[auth]['with']
            self.assertIn('vars.STAGING_GCP_PROJECT && vars.STAGING_PREVIEW_WIF_PROVIDER || vars.WIF_PROVIDER', with_['workload_identity_provider'])
            self.assertIn('vars.STAGING_GCP_PROJECT && vars.STAGING_PREVIEW_SA || vars.DEPLOYER_STAGING_SA', with_['service_account'])
        preview = self.workflow('pr-preview.yml')
        self.assertIn('vars.STAGING_GCP_PROJECT || vars.GCP_PROJECT', preview['env']['PROJECT'])
        self.assertIn('vars.STAGING_GCP_PROJECT && vars.STAGING_HOSTING_SITE', preview['env']['STAGING_SITE'])
        build = next(s for s in preview['jobs']['preview']['steps'] if s.get('working-directory') == 'web')
        self.assertEqual(build['env']['VITE_APP_HOSTS'], "${{ vars.STAGING_GCP_PROJECT && 'onolys-staging-app.web.app' || '' }}")
        self.assertIn('vars.STAGING_ISOLATED_VITE_FIREBASE_API_KEY', build['env']['VITE_FIREBASE_API_KEY'])
        self.assertIn('release_target.py hosting web/firebase.preview.json', str(preview))
        # The newest preview revision is left for the sweep, so the sweep must run in isolated mode too.
        sweep = self.workflow('deploy-staging.yml')['jobs']['sweep-previews']
        self.assertNotIn('STAGING_GCP_PROJECT', str(sweep.get('if', '')))
        self.assertIn('STAGING_DEPLOYER_SA', str(sweep['steps']))
        cleanup = self.workflow('pr-preview-cleanup.yml')
        self.assertIn('vars.STAGING_GCP_PROJECT', cleanup['env']['GCP_PROJECT'])
        self.assertIn('vars.STAGING_HOSTING_SITE', cleanup['env']['PREVIEW_SITE'])

    def test_reusable_auth_override_retains_fallback(self):
        workflow = self.workflow('_deploy-cloudrun.yml')
        auth = next(step for step in workflow['jobs']['deploy']['steps'] if step.get('uses', '').startswith('google-github-actions/auth@'))
        self.assertIn('inputs.workload_identity_provider || vars.WIF_PROVIDER', auth['with']['workload_identity_provider'])
        self.assertIn('inputs.service_account ||', auth['with']['service_account'])


if __name__ == '__main__':
    unittest.main()
