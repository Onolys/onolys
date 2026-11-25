---
status: done
summary: Pin session inputs to each MITI run and improve coding with bounded cost
date: 2026-11-24
---

# Session inputs and MITI runs

## TL;DR

The brainstorm is complete. The user approved the low-complexity MITI engine direction and including database rewiring in the same future PR. This remains proposed future work: each run carries a fixed receipt of its inputs, upload and the canonical change goal stay with the session, and evidence handling improves within the existing processing stages. Keep the current failed-retry-only policy. Push this branch; open one PR later, with no PR now. No further questions or approval gate remain for this brainstorm.

## Problem

A clinician uploads a recording, confirms the clinician speaker and final change goal, then receives MITI 4.2.1 coding, a report and basic tips. Every result needs to remain explainable from the transcript and inputs actually used. The user wants this to work for any valid MI session with low implementation complexity and processing time.

## Repository facts

The [mission](../../mission.md) governs the work. The [run route](../../../api/src/onolys_api/routes/runs.py) already guards starts through a transaction, reserves quotas and creates a run ID. Manual retries of failed runs create another ID and recover the previous preset, run count and coded span. A completed report blocks deliberate reruns through the current `report_ready` policy.

The [worker](../../../api/src/onolys_api/jobs/run.py) reads the current session goal, speaker and language alongside the transcript when evaluation executes. Several inputs can therefore come from session state after the run was created. Reports already carry `run_id` ownership. Publication transactionally stores the report, updates session and browser status, records run output fields and releases the quota slot. The worker separately marks the run done. Browser progress has its own status document.

The [transcript model](../../../api/src/onolys_api/repo/models.py) supports inline content or a blob pointer. There is a single `current` transcript in this workflow. Its storage method permits replacement and has no persisted transcript hash today. The proposed write-once guarantee needs implementation and validation.

## Decision log

| Decision | Status and reason |
|---|---|
| Apply the approved engine changes to any valid MI session | User approved. Example-specific scoring would defeat the purpose. |
| Include database rewiring in the same PR | User approved. Run ownership and reproducibility belong with this change. |
| Keep upload and the canonical change goal with the session | User requested. A run records the values it consumed. |
| Keep scope within MITI 4.2.1 | Governing mission. Self-ratings remain contextual and never influence coding. |
| Reuse existing storage, transactions and public contracts where practical | Proposed default to limit work and compatibility risk. |
| Retain failed-retry-only behavior; exclude successful-session reruns | User resolved Q1. A completed report remains final. |
| Push this branch and open one PR later | User resolved Q2. No PR now. |

## Proposed design

### Session and run ownership

The session owns its source, uploaded audio, canonical goal and existing transcript. Keep one write-once current transcript until editing or retranscription becomes supported. At run start, pin its reference and content identity, then validate that identity when consumed. Persisting a hash during transcription or deriving it from the already loaded transcript at run start are implementation options. Avoid additional uploads, rewrites or duplicate full transcript reads solely to create the receipt.

The run snapshot captures the goal, confirmed clinician speaker, effective language, coded span, STT details, rating revision reference, preset, run count and relevant engine provenance. Capture requested settings and actual worker settings separately where execution can differ. Final submit already sets the session goal. That session value remains canonical. The rating revision remains contextual metadata.

Use existing report storage with run ownership and separate browser status. Preserve transactions, authorization, deletion and quotas. Add compatibility handling per legacy run and mark unavailable historical provenance as unknown. Avoid a bulk migration or invented historical receipts. A missing or mismatched pinned source fails evaluation before any model call, using the existing failure display and an internal structured reason without transcript content. A pinned run never falls back to another transcript.

### A concrete run sequence

1. Upload, transcribe, confirm the speaker and finalize the goal.
2. Run A starts and pins its input receipt.
3. An automatic worker retry keeps A's ID and pinned inputs.
4. A terminal failure leaves A failed. When the existing failure policy permits a manual retry, it creates Run B using the same pinned inputs. A successful run cannot be retried.
5. B alone publishes its report if B succeeds. Existing transactional guards prevent concurrent starts.

Retries reuse failed pinned inputs. Editing finalized goals or speakers and running with corrected inputs are separate product behaviors beyond this PR's recommended scope.

Add a previous-run reference only if a concrete consumer needs it. The retry mechanism can copy the prior receipt without a new lineage model.

Successful-session reruns are excluded. The existing policy keeps a completed report final; only failed runs may be retried under the existing failure policy.

### MITI engine

This section records the scope from the user's earlier explicit approval. Check complete ordered clinician coverage using turn IDs and spans, including explicit uncoded speech. Resolve one persuasion-family slot deterministically. Give client acknowledgements and permission enough chronological context through context-only turns, using the same batch plan and bounds where practical. Count only turns owned by the batch and validate overlap boundaries.

Validate evidence against the source and preserve exact quotations. Score globals when sparse evidence supports a rating. Show unavailable globals as no score in the UI and `null` in the structured report, using a compatible shape where possible. Leave dependent summary scores unavailable in both representations. Old reports retain their stored values. Remove misleading automatic midpoint ratings.

Keep the default processing stages and bounded retries, with no extra model round trip on the normal path. Prefer compact validated anchors and bounded context to repeating the selected transcript in every request. Group coding and reporting lightly while preserving callers. Add no scoring protocols or example-specific rules.

## Goals, non-goals and anti-goals

Success means traceable coding, stable run inputs and a report that matches its transcript. Diagnosis, clinical-correctness judgments, official MITI claims, transcript editing and new protocol scoring remain outside scope. Invented evidence, hidden input changes, misleading scores and uncontrolled processing cost count as failures.

## Open risks and cheap checks

| Risk | Cheapest useful check |
|---|---|
| Coding quality or context regresses | Check deterministic validity, batch edges and coverage. Compare matched held-out human coding under fixed settings. |
| Inputs change after start | Mutate the session goal in a test and verify the original run receipt and report. |
| Retry or delivery publishes the wrong report | Exercise races, cancellation, redelivery and owner access with targeted tests. |
| Context increases cost or delay | Compare request counts, tokens and p50/p95 runtime on the same inputs, including 6,000 words. |

Surface material quality, cost or latency changes before shipping. Small samples support limited observations and cannot establish broad accuracy or reliable tail latency.

## Resolved questions and handoff

**Q1 — Successful-session reruns:** retain the current failed-retry-only policy. Do not add reruns after success.

**Q2 — PR destination:** push `session-report-ux`; open one PR later. Do not open a PR now.

The approved engine and database directions above are proposed future work, not implementation delivered by this brainstorm. Finalizing this document completes the current task; no further questions or approval gate remain.
