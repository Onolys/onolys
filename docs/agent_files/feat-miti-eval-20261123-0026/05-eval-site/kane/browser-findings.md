# Task 12 browser verification — 2026-11-23

Browser: Kane CLI 0.10.8, local headless Chrome. Staging site: https://onolys-eval-staging.web.app. API: the canonical staging Cloud Run service. All browser interaction used Kane; no direct browser automation framework was used.

## Observed results

| Journey | Result | Evidence |
|---|---|---|
| Anonymous access | PASS: sign-in form and its email/password/Google controls visible; anonymous `/v1/me` returned 401 | [Test Manager](https://test-manager.lambdatest.com/projects/01M839T642F9D6MNC4ZBY014G5/test-cases/01M83A1JBW5WMXYPSA9CEC78X5) |
| Verified disposable non-allowlisted account | Visible `Not allowed` and inaccessible New run PASS after authenticating through normal Firebase SDK session persistence. Browser network-403 capture was stopped; API 403 is separately verified by the deployment agent | Private retry session `21a73046-c188-4a90-9aca-5417b29390b6` |
| Dataset defaults and planned count | PASS: allowlisted New run, all eight CASAA sessions, Human + production MITI engine + production preset defaults, 16 planned units; Human + two AI engines × two presets × three repeats displayed 104 units. Start was not clicked | [Test Manager](https://test-manager.lambdatest.com/projects/01M839T642F9D6MNC4ZBY014G5/test-cases/01M83AGKFPEHN79PD841Z4ZJHY) |
| Compare, repeats, JSON, history and rerun form | PASS: completed no-Human run showed 16 metric rows without Human/error columns; synthetic unit JSON opened; completed Human run showed Human/difference/MAE columns and successful-unit MAE caption; three-repeat run displayed means/ranges/n=3; history showed input/status/tokens/estimated cost and expanded version/SHA/model provenance; rerun prefilled the saved input and engine/preset. No additional run was started | [Test Manager](https://test-manager.lambdatest.com/projects/01M839T642F9D6MNC4ZBY014G5/test-cases/01M83APWW9P9Z8WAQ04AB1RPPX) |
| Upload form, named-speaker preparation | PASS: actual synthetic TXT upload, known fixture goal and `en`, Prepare upload, real clinician speaker gate, clinician selection confirmed and ready state; production engine/preset defaults, Human absent without gold, optional gold picker and audio-support controls verified. Start was not clicked | [Test Manager](https://test-manager.lambdatest.com/projects/01M839T642F9D6MNC4ZBY014G5/test-cases/01M83B9E23QY3VESA35N22Q5QR) |
| Actual tab close while background unit runs | BLOCKED by browser-session setup: the one-off browser opened a fresh unauthenticated context. No queued/running browser assertion or actual tab close occurred before server completion; AC3 persistence after actual tab closure is not proven | [Test Manager](https://test-manager.lambdatest.com/projects/01M839T642F9D6MNC4ZBY014G5/test-cases/01M83B6MZ83CN4W5FWPBTW5NPJ) |

The tab-close attempt used exactly one actual Rounder MITI-lean/Claude unit, run `42e5b98082b84dc1a6a28a5ca8411804`, created by the deployment agent. Server timestamps independently showed work starting at `04:38:49.562275Z` and finishing at `04:40:00.928848Z`, done 1/1. Those server observations establish engine execution, not the missing browser-close condition. No second provider run was started for this attempt.

## Completed-run measurements

| Run | Tool duration | Completed browser steps | Reported credits |
|---|---:|---:|---:|
| Initial two-test auth suite | 2m25s | 11 | 54.0054175 |
| Dataset defaults/count | 2m28s | 19 | 41.47461 |
| Compare/history/rerun form | 4m17s | 32 | 91.1058775 |
| Corrected upload | 2m02s | 17 | 45.057035 |
| Tab-close setup block | 50s | 3 | 14.021825 |

The bounded forbidden retry proved its first visible-access check in 47.7s/19.403235 credits; its stopped second step has no complete billing total. The stopped first upload attempt also has no final total. Do not infer an all-attempt total from the completed-run table.

## Product finding

Low severity, cosmetic: the production MITI engine is rendered as `MITI lean (prod) (prod)` in New run. The production marker appears twice. Observed in the actual Upload form; private screenshot `/root/.cache/onolys-eval/kane-smoke/duplicate-prod-label.jpg`. No source fix was made by the browser verifier.

## Test setup and tool limits

- The existing allowlisted account was used only after the user approved the specific verified-email update and the deployment agent confirmed `/v1/me` 200. Browser setup exchanged a legitimate custom token through the official Firebase SDK and serialized its normal authenticated user persistence. This proves the application auth gate; it does not prove email/password or Google-provider sign-in.
- Secret user JSON stayed in external cache files with `secret: true`. The initial forbidden test failed because Kane generated a literal variable placeholder for the localStorage **key** while resolving only its value. A private runtime copy with the public Firebase storage key literal fixed setup; the value remained secret. The committable generated template retains parameter placeholders and needs this documented runtime workaround.
- The forbidden retry's visible access-denied check passed. The subsequent browser-network inspection was bounded and stopped. A brief overlap with the first positive run occurred, but whether the browser contexts interfered is unproven. Do not label this a product failure or a proven network-capture defect. The disposable account was deleted afterward by the deployment agent.
- The first upload attempt selected the named synthetic file but omitted the required fixture goal and language. Preparation stayed disabled, so that attempt was stopped. This was an incomplete test setup, not an upload defect. The approved corrected attempt explicitly supplied the known synthetic goal and `en` and passed preparation, actual speaker choice, ready state and defaults. No disabled-control product failure was found.
- One-off Kane runs create fresh contexts; each independent positive journey needs an explicit SDK bootstrap. Assuming a prior one-off context remained authenticated caused the tab-close proof to miss its natural execution window.

## Assurance provenance and coverage limits

The approved PRD was ingested through Kane assurance and produced seven proposed use cases. The orchestrator reviewed the complete generated proposal and approved focused design. UC1 produced two requirement-tagged test files; their narrow step-body changes were reviewed before execution, with metadata/headings/tags preserved. The exact selection dry-run was valid with no unresolved-variable warnings.

UC2 generation failed with `AGENT_FAILED` / `ILLEGAL_EDGE: t1.automates: automates dst must be scenario, got gap`. One explicitly approved resume of `design-20261123T041918-dc9db6` failed identically. No further paid generation was attempted. The orchestrator approved supplemental one-off Kane objectives from the same PRD; Kane authored their browser actions. These supplemental results are **not assurance coverage**. The initial assurance run reported 3% project coverage with only one criterion proven; that figure must not be represented as product acceptance coverage.

Test Manager project: `Onolys MITI Eval` (`01M839T642F9D6MNC4ZBY014G5`), folder `Staging` (`01M839W5JMKBHQ3H8Q57368ZFH`). Only the branch artifact folder was assurance-linked. Supplemental runs used a separate unlinked private folder and a bounded CLI project/folder configuration transaction; each transaction restored the exact original project and folder. No onboarding preferences were written. CLI creation exposes no privacy option; the project uses the existing account's access defaults.

## Reproduction and evidence handling

Every Kane command used `KANE_CLI_USER_AGENT=codex`. The actual command shapes were:

```bash
kane-cli context ingest ../PRD.md --project <Onolys-project-id> --mode agent
kane-cli design tests --use-case uc-1 --max 2 --mode agent --allow-unreviewed
kane-cli context sessions save <session-id> --yes --mode agent
kane-cli testrun run <two-generated-test-files> --dry-run --agent < /dev/null
kane-cli testrun run <two-generated-test-files> --headless --agent < /dev/null
kane-cli testmd run <private-runtime-test-copy> --agent --headless
kane-cli run <approved-objective> --agent --headless --variables-file <external-secret-file>
```

All browser processes are terminal, and the exact original CLI project/folder were restored after the final objective. Browser-owned plaintext secret variable files and private variable copies were removed after use; the deployment agent confirmed its task auth cache, temporary identity proof and auth helpers were deleted. Existing global Kane sign-in and cloud ADC credentials were left untouched. The project link excludes the personal `lastUserId`.

The branch folder retains only the project link, two generated test templates and this sanitized report. All variable files, private runtime copies, recordings, screenshots, raw logs and evidence packs remain outside git, under `/root/.cache/onolys-eval/kane-smoke/` or Kane's session cache. No raw transcript, gold contents, quotations, real speaker identities, authentication state or credentials are included here. The deployment agent owns the final commit; the browser verifier made no application-source changes or commits.
