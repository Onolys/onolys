# Your rating

How should I think about the clinician's own rating of a session? What users can enter today, and what the dormant rating card does.

**Audience:** users and contributors.

## What is offered today

Clinician self-rating is not offered. The web flag `VITE_RATING_ENABLED` is off in every build (`web/.env.example` sets it to `false`, and no deploy workflow sets it), and the rating card code is dormant.

With the flag off, the only input a user gives is:

- Audio and a "Change goal" on the upload screen. Start saves the session with a final "no rating" card (`no_rating`), so the evaluation runs on Onolys's own reading.
- The speaker pick, once the transcript is ready (the speaker gate, shown until speakers are confirmed).

There is no "Your rating" step in the session timeline and nothing to fill in while processing runs. The processing screen shows "You can close this tab — we'll keep working" from validation through the evaluation run, so a user can close the tab once upload completes (except to pick speakers, where the hint reads "We'll wait here for your choice").

## Dormant behaviour (flag on)

`ratingEnabled()` (web `config.ts`) is true only when `VITE_RATING_ENABLED=true` is set at build time. Only then does the timeline add a "Your rating" step and the session page show a "Your rating" card (MITI 4.2.1 items); the upload screen's "Change goal" is shown only when the flag is off. If a rating is typed during processing, the background hint still holds because the card autosaves a server-side draft.

- Change goal and an optional coded from-to span.
- Four global ratings (1-5 score from a list, plus a free-text reason and optional example).
- Ten behaviour counts, each with a note.
- Additional notes (free text).

The card shows in every session state except `deleting`, is autosaved to the server as a draft (`PUT /sessions/{id}/rating`, `final: false`, 2 s debounce, also on blur and page hide), and the draft is restored on reopen (`GET /sessions/{id}/rating`). "Submit rating" or "No rating" makes it final and read-only. Once the report is ready the card is read-only.

API details: [../reference/public-api.md](../reference/public-api.md). Mission note on rating cards: [../mission.md](../mission.md).
