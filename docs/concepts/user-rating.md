# Your rating

How should I think about the clinician's own rating of a session? What users can enter today, and what the dormant rating card does.

**Audience:** users and contributors.

## What is offered today

Clinician self-rating is not offered. The web flag `VITE_RATING_ENABLED` is off in every build (`web/.env.example` sets it to `false`, and no deploy workflow sets it), and the rating card code is dormant.

With the flag off, the only input a user gives is:

- Audio and a "Change goal" on the upload screen. Start saves the session with a final "no rating" card (`no_rating`), so the evaluation runs on Onolys's own reading.
- The speaker pick, once the transcript is ready (the speaker gate, shown until speakers are confirmed).

There is no rating step in the session timeline and nothing to fill in while transcription runs, so a user can close the tab after upload completes (except to pick speakers).

## Dormant behaviour (flag on)

If `VITE_RATING_ENABLED=true` is set at build time, the session page shows a "Your rating" card (MITI 4.2.1 items):

- Change goal and an optional coded from-to span.
- Four global ratings (1-5 score from a list, plus a free-text reason and optional example).
- Ten behaviour counts, each with a note.
- Additional notes (free text).

The card shows in every session state except `deleting`, is autosaved to the server as a draft (`PUT /sessions/{id}/rating`, `final: false`, 2 s debounce, also on blur and page hide), and the draft is restored on reopen (`GET /sessions/{id}/rating`). "Submit rating" or "No rating" makes it final and read-only. Once the report is ready the card is read-only.

API details: [../reference/public-api.md](../reference/public-api.md). Mission note on rating cards: [../mission.md](../mission.md).
