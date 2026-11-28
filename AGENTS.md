# Agent instructions

`docs/mission.md` is the governing mission statement. Read it before any work. It wins over other docs when they conflict.

The scope is MITI 4.2.1 coding of a session plus a report and basic tips. Do not build outside that scope (diagnosis, clinical-correctness judgement, scoring other protocols, or claiming official MITI status) without the user's explicit approval.

Never invent quotations, speaker identities, or timestamps.

## Where docs go

| Path | Purpose | Audience |
|---|---|---|
| `docs/mission.md` | Governing mission and scope | Everyone |
| `docs/architecture.md` | High-level design: how the system fits together | Everyone |
| `docs/concepts/` | How should I think about this? Behavior that crosses components | Users and contributors |
| `docs/implementation/` | How is this implemented? Private implementation details | Maintainers and coding agents |
| `docs/reference/` | What exactly is supported? Precise, lookup-oriented facts | Users |
| `docs/decisions/` | Why is it like this? Architecture decision records | Contributors |
| `docs/testing/` | How to test, and what to verify before a release | Contributors |
| `docs/specs/` | Normative behavior contracts with acceptance criteria | Contributors and coding agents |
| `docs/contracts/` | Pointer to the generated public API schemas (`public/`) | Web, api, and coding agents |
| `docs/rules/` | Coding rules for all code; design rules for UI | Contributors and coding agents |
| `docs/agent_files/` | Branch-scoped agent artifacts, one folder per branch | Coding agents |

The MITI engine documents itself in `engines/miti/README.md`.

## Rules

All agents must read and follow `docs/rules/coding-rules.md` every time, before changing code.

Agents working on UI (`web/`, any UI) must also read and follow `docs/rules/design-rules.md`.

## Agent-generated files

All agent-generated, branch-related files (PRDs, task lists, reviews, plans, notes) go under `docs/agent_files/<branch-name-timestamp>/`.

Replace `/` in the branch name with `-`. Create that folder once per branch and reuse it.
