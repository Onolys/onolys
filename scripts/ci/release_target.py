#!/usr/bin/env python3
"""Validate explicit release target bundles and create local Hosting target mappings.

Staging and eval always run isolated (STAGING_GCP_PROJECT / EVAL_GCP_PROJECT required).
No cloud commands or credentials are used here.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys


def validate(role: str, env: dict[str, str]) -> None:
    prefix = role.upper()
    project = env.get(f'{prefix}_GCP_PROJECT', '')
    if not project:
        raise ValueError(f'{prefix}_GCP_PROJECT must be onolys-{role}')
    if project != f'onolys-{role}':
        raise ValueError(f'{prefix}_GCP_PROJECT must be onolys-{role}')
    values = {field: env.get(f'{prefix}_{field}', '') for field in ('WIF_PROVIDER', 'DEPLOYER_SA', 'HOSTING_SITE')}
    missing = [f'{prefix}_{field}' for field, value in values.items() if not value]
    if missing:
        raise ValueError('Active isolated target requires ' + ', '.join(missing))
    if not re.fullmatch(r'projects/[0-9]+/locations/global/workloadIdentityPools/[a-z0-9-]+/providers/[a-z0-9-]+', values['WIF_PROVIDER']):
        raise ValueError(f'{prefix}_WIF_PROVIDER must be a full workload identity provider resource name')
    if not re.fullmatch(r'[a-z][a-z0-9-]*@' + re.escape(project) + r'\.iam\.gserviceaccount\.com', values['DEPLOYER_SA']):
        raise ValueError(f'{prefix}_DEPLOYER_SA must belong to {project}')
    if role == 'staging':
        for field in ('API_KEY', 'AUTH_DOMAIN', 'APP_ID'):
            value = env.get(f'STAGING_ISOLATED_VITE_FIREBASE_{field}', '')
            if not value or any(char.isspace() for char in value):
                raise ValueError(f'STAGING_ISOLATED_VITE_FIREBASE_{field} is required for isolated staging')
        if env['STAGING_ISOLATED_VITE_FIREBASE_AUTH_DOMAIN'] != 'onolys-staging.firebaseapp.com':
            raise ValueError('Isolated staging must use its own Firebase auth domain')
        if not re.fullmatch(r'1:[0-9]+:web:[a-z0-9]+', env['STAGING_ISOLATED_VITE_FIREBASE_APP_ID']):
            raise ValueError('Isolated staging needs a Firebase web app ID')
    if role == 'eval':
        # Eval signs in through its own project's Firebase web app, never prod's.
        for field in ('API_KEY', 'AUTH_DOMAIN', 'APP_ID'):
            value = env.get(f'EVAL_VITE_FIREBASE_{field}', '')
            if not value or any(char.isspace() for char in value):
                raise ValueError(f'EVAL_VITE_FIREBASE_{field} is required for eval')
        if env['EVAL_VITE_FIREBASE_AUTH_DOMAIN'] != 'onolys-eval.firebaseapp.com':
            raise ValueError('Eval must use its own Firebase auth domain')
        if not re.fullmatch(r'1:[0-9]+:web:[a-z0-9]+', env['EVAL_VITE_FIREBASE_APP_ID']):
            raise ValueError('Eval needs its own Firebase web app ID')
    site = values['HOSTING_SITE']
    if role == 'staging' and site != 'onolys-staging-app':
        raise ValueError('STAGING_HOSTING_SITE must be onolys-staging-app (the supported callback origin)')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,28}[a-z0-9]', site):
        raise ValueError(f'{prefix}_HOSTING_SITE must name a new isolated Firebase Hosting site')


def validate_preview(env: dict[str, str], web: bool = True) -> None:
    """PR previews run in the isolated staging project with their own limited identity; never fall back to another one."""
    project = env.get('STAGING_GCP_PROJECT', '')
    if project != 'onolys-staging':
        raise ValueError('STAGING_GCP_PROJECT must be onolys-staging')
    provider = env.get('STAGING_PREVIEW_WIF_PROVIDER', '')
    account = env.get('STAGING_PREVIEW_SA', '')
    site = env.get('STAGING_HOSTING_SITE', '')
    missing = [name for name, value in (('STAGING_PREVIEW_WIF_PROVIDER', provider), ('STAGING_PREVIEW_SA', account),
                                        ('STAGING_HOSTING_SITE', site)) if not value]
    if missing:
        raise ValueError('Isolated PR previews require ' + ', '.join(missing)
                         + ' (terraform outputs pr_preview_wif_provider / pr_preview_service_account)')
    if not re.fullmatch(r'projects/[0-9]+/locations/global/workloadIdentityPools/github-pr/providers/github-pr', provider):
        raise ValueError('STAGING_PREVIEW_WIF_PROVIDER must be the github-pr provider in the separate github-pr pool, not the deployer provider')
    if account != f'pr-preview-staging@{project}.iam.gserviceaccount.com':
        raise ValueError(f'STAGING_PREVIEW_SA must be pr-preview-staging@{project}.iam.gserviceaccount.com')
    if site != 'onolys-staging-app':
        raise ValueError('STAGING_HOSTING_SITE must be onolys-staging-app')
    if web:
        for field in ('API_KEY', 'AUTH_DOMAIN', 'APP_ID'):
            value = env.get(f'STAGING_ISOLATED_VITE_FIREBASE_{field}', '')
            if not value or any(char.isspace() for char in value):
                raise ValueError(f'STAGING_ISOLATED_VITE_FIREBASE_{field} is required for isolated previews')
        if env['STAGING_ISOLATED_VITE_FIREBASE_AUTH_DOMAIN'] != 'onolys-staging.firebaseapp.com':
            raise ValueError('Isolated previews must use the staging Firebase auth domain')


def configure_hosting(config: Path, project: str, target: str, site: str) -> None:
    """Map only the requested target in this job's checkout; retain checked-in mappings."""
    data = json.loads(config.read_text())
    hosting = data.get('hosting', [])
    hosting = [hosting] if isinstance(hosting, dict) else hosting
    if not any(entry.get('target') == target for entry in hosting):
        raise ValueError(f'{config} has no Hosting target {target}')
    rc = config.parent / '.firebaserc'
    mapping = json.loads(rc.read_text()) if rc.exists() else {}
    mapping.setdefault('targets', {}).setdefault(project, {}).setdefault('hosting', {})[target] = [site]
    rc.write_text(json.dumps(mapping, indent=2) + '\n')


def configure_voice(config: Path, origin: str) -> None:
    # The api service env VOICE_URL is wss://<host>.run.app; Cloud Run status.url is https://<host>.run.app. Same origin.
    if origin.startswith('wss://'):
        origin = 'https://' + origin[len('wss://'):]
    if not re.fullmatch(r'https://[a-z0-9][a-z0-9.-]*\.run\.app', origin):
        raise ValueError('Voice URL must be an exact HTTPS Cloud Run origin')
    data = json.loads(config.read_text())
    entry = next(item for item in data['hosting'] if item.get('target') == 'app-staging')
    changed = 0
    for rule in entry.get('headers', []):
        for header in rule.get('headers', []):
            if header.get('key') == 'Content-Security-Policy':
                header['value'], count = re.subn(r'wss://onolys-voice-staging-[a-z0-9.-]+\.run\.app',
                                                origin.replace('https://', 'wss://', 1), header['value'])
                changed += count
    if changed != 1:
        raise ValueError('Expected exactly one staging voice CSP origin')
    config.write_text(json.dumps(data, indent=2) + '\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('staging')
    sub.add_parser('eval')
    sub.add_parser('preview')
    sub.add_parser('preview-cleanup')
    voice = sub.add_parser('voice')
    voice.add_argument('config', type=Path)
    voice.add_argument('origin')
    hosting = sub.add_parser('hosting')
    hosting.add_argument('config', type=Path)
    hosting.add_argument('project')
    hosting.add_argument('target')
    hosting.add_argument('site')
    args = parser.parse_args()
    try:
        if args.command == 'voice':
            configure_voice(args.config, args.origin)
        elif args.command == 'hosting':
            configure_hosting(args.config, args.project, args.target, args.site)
        elif args.command in ('preview', 'preview-cleanup'):
            validate_preview(dict(os.environ), web=args.command == 'preview')
        else:
            validate(args.command, dict(os.environ))
    except (ValueError, OSError) as exc:
        print(f'Invalid release target: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
