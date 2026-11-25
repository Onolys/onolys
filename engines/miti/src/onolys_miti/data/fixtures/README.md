# Synthetic fixtures

All transcripts in this directory and `evaluation/` are SYNTHETIC role-plays: invented,
fictional people, written for testing. They are not recorded patient sessions.

- `good_practice.json`: good MI practice.
- `poor_practice.json`: poor MI practice, including Persuade and Confront.
- `short_session.json`: short 8-minute session.
- `evaluation/transcript.json`: the good-practice transcript used for report fixtures.

Transcript JSON files follow transcript.v1; fixture metadata stays in this README.

Manual-alignment fixtures (hand-authored, no model output):

- `batch_edge.json`: 1,446 words, 20 minutes, 27 clinician volleys. The first
  volley groups `b01a` and `b01b` across client `ack`: `yeah`. That facilitative
  acknowledgement does not interrupt a volley (manual pp.13, 15–16). Every other
  ordinary client reply has at least three words and breaks the volley under
  the engine's size approximation. `expected.yaml` lists every clinician turn
  group explicitly; client turns are never codable.
- The 25/26 batch boundary is deliberate: v25 (`b25`) asks
  `May I offer a suggestion about fitting a short walk into your lunch break?`
  Client `permission` answers `yeah`, so this acknowledgement **does** break
  the volley as an answer to a direct question (manual pp.15–16). v26 (`b26`)
  contains `You should put a walk on your calendar today.` and
  `With your permission, I suggest trying a ten minute walk after lunch tomorrow.`
  Permission can precede advice (pp.18–20); the previous clinician volley must
  reach the second batch as context in the later context-alignment task.
- The v26 hand instances deliberately propose both persuasion codes on distinct
  utterances. The target is one Persuade with Permission and zero Persuade
  (one persuasion slot, p.13; permission precedence within an utterance, p.20;
  its extension across the volley is PRD D3). Before the persuasion-slot fix,
  `apply_rules` counts both: exactly one extra Persuade, one extra Total MINA,
  and one double-counted volley (`v26`). `pre_alignment` records that discrepancy;
  the tests require the manual target once the slot rule is present.
- `sparse_evidence.json`: a four-minute, five-volley exchange with one brief
  change-talk statement (`I could try a walk.`), no sustain talk, and few global
  evidence quotes. SST is hand-set to 5, acceptable range 4–5 (p.38 FAQ 6, p.7):
  absence of sustain talk does not prevent a high rating. It has no SST evidence
  quotes, so it can expose the evidence-count reset in the later globals task.
  These are test targets, not clinical assessments or independent coder scores.

For both fixtures, `expected.yaml` gives all ten count targets, a page-cited
reason per code, four global scores/ranges and summary targets so existing
fixture readers can parse them. Every evidence and utterance quote is an exact
substring of its synthetic turn. The offline audit discovers both fixtures from
that file. Tests stress 6,000 words in a valid 24-minute coded span by constructing
turns in memory and checking three disjoint rendered batches; that larger
transcript is not committed. The new fixtures have no live-model recordings or
new golden responses; existing good-practice goldens remain unchanged.
