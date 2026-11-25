#!/usr/bin/env python3
"""Validate explicit release target bundles and create local Hosting target mappings.

*_GCP_PROJECT is the activation switch: prepare the other repository variables first.
No cloud commands or credentials are used here.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys


LEGACY_SITES = {'onolys-app', 'onolys-app-staging', 'onolys-eval-staging'}


def validate(role: str, env: dict[str, str]) -> None:
    prefix = role.upper()
    project = env.get(f'{prefix}_GCP_PROJECT', '')
    if not project:
        return
    if project != f'onolys-{role}':
        raise ValueError(f'{prefix}_GCP_PROJECT must be onolys-{role}; clear it to use the legacy target')
    values = {field: env.get(f'{prefix}_{field}', '') for field in ('WIF_PROVIDER', 'DEPLOYER_SA', 'HOSTING_SITE')}
    missing = [f'{prefix}_{field}' for field, value in values.items() if not value]
    if missing:
        raise ValueError('Active isolated target requires ' + ', '.join(missing))
    if not re.fullmatch(r'projects/[0-9]+/locations/global/workloadIdentityPools/[a-z0-9-]+/providers/[a-z0-9-]+', values['WIF_PROVIDER']):
        raise ValueError(f'{prefix}_WIF_PROVIDER must be a full workload identity provider resource name')
    if not re.fullmatch(r'[a-z][a-z0-9-]*@' + re.escape(project) + r'\.iam\.gserviceaccount\.com', values['DEPLOYER_SA']):
        raise ValueError(f'{prefix}_DEPLOYER_SA must belong to {project}')
    if role == 'staging':
        # Staged separately so preparing a new web app cannot change the legacy web build.
        for field in ('API_KEY', 'AUTH_DOMAIN', 'APP_ID'):
            value = env.get(f'STAGING_ISOLATED_VITE_FIREBASE_{field}', '')
            if not value or any(char.isspace() for char in value):
                raise ValueError(f'STAGING_ISOLATED_VITE_FIREBASE_{field} is required for isolated staging')
        if env['STAGING_ISOLATED_VITE_FIREBASE_AUTH_DOMAIN'] != 'onolys-staging.firebaseapp.com':
            raise ValueError('Isolated staging must use its own Firebase auth domain')
        if not re.fullmatch(r'1:[0-9]+:web:[a-z0-9]+', env['STAGING_ISOLATED_VITE_FIREBASE_APP_ID']):
            raise ValueError('Isolated staging needs a Firebase web app ID')
    site = values['HOSTING_SITE']
    if role == 'staging' and site != 'onolys-staging-app':
        raise ValueError('STAGING_HOSTING_SITE must be onolys-staging-app (the supported callback origin)')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,28}[a-z0-9]', site) or site in LEGACY_SITES:
        raise ValueError(f'{prefix}_HOSTING_SITE must name a new isolated Firebase Hosting site')


def configure_hosting(config: Path, project: str, target: str, site: str) -> None:
    """Map only the requested target in this job's checkout; retain checked-in legacy mappings."""
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
        else:
            validate(args.command, dict(os.environ))
    except (ValueError, OSError) as exc:
        print(f'Invalid release target: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
