---
status: in-progress
summary: Public nav, compact footer, sessions split and MITI-style report with public sample — index of sub-projects
date: 2026-11-23
---
# Public nav, sessions split & MITI-style report

## Sub-projects
| Folder | Scope | Branch / repo |
|---|---|---|
| 01-app-chrome-routing | iaudit web chrome/routing (footer, nav, New Session chooser, Sessions list) | feat/public-nav-sample-report (this branch) |
| 02-report-redesign | report view, sample fixture, tips prompt | built on feat/public-nav-sample-report-sp2, then merged |
| 03-miti-landing | miti repo landing | feat/compact-footer-sample-redirect, separate PR |

## Dependency graph
01 ∥ 02 ∥ 03 (independent). 03 deploys only after app /sample is live.

## Locked decisions
See [brainstorm.md](brainstorm.md) decision log.

## Mockup
- https://claude.ai/artifact/1fj2vL8NmuvhRs7BRfWXAN
- [02-report-redesign/mockup.html](02-report-redesign/mockup.html)

## Cross-cutting risks
- Land before feat/design-system.
- Prod reports from older engines.
- miti redirect deploy order (after app /sample live).
