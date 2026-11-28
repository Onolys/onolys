# Owner follow-ups

Things only the owner can do (cloud consoles, account settings, approvals). Agents add and remove items here as work lands. Newest section first.

## Admin site retirement (from branch chore/remove-admin-frontend, 2026-11-28)

- [ ] Remove `admin.onolys.com`, `onolys-admin.web.app` and `onolys-admin-staging.web.app` from Firebase authorized sign-in domains (`infra/identity.tf` lines 25-27, then `terraform apply`). Do this BEFORE step 2, so no one can take over a host that is still allowed to sign users in.
- [ ] Delete the admin Firebase Hosting sites (`onolys-admin`, `onolys-admin-staging`) and the `admin.onolys.com` DNS record.

## Claude docs

- [ ] Rename the doc "Onolys code structure: rules draft" to "Onolys revamp: rules and changes" on claude.ai (the tool could not rename it).
- [ ] Delete the superseded doc "Onolys MITI engine: redesign notes" under Artifacts in Claude (the tool is not allowed to delete it).
