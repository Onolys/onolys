---
status: done
summary: MITI 4.2.1 deterministic rules aligned; semantic coding and documented engineering approximations remain unvalidated.
date: 2026-11-24
---
# Manual alignment audit

Source: [MITI 4.2.1 manual, CASAA](https://casaa.unm.edu/assets/docs/miti4_21.pdf). Printed pages below were checked offline against the local extracted manual at `/tmp/claude-0/-root-projects/ef361743-160c-44e1-ab21-8519019ace47/scratchpad/miti.txt` (Revised June 2015 headers). No network was used. This is an audit of specified rules and deterministic behavior at `6af8a73`, not certified human coding, an accuracy evaluation or an official MITI product.

Repository references below are relative to `engines/miti/`; line numbers describe that implementation commit. **Match** means the existing rule matches the cited provision; **fixed here** identifies SP02 changes; **approximation** identifies an engineering choice rather than a manual requirement. Semantic judgments remain model proposals even when the prompt matches the manual.

## Parsing and counting

| Rule | Manual provision | Implementation and status |
|---|---|---|
| Clinician volleys and utterances | E.1, pp.13–14: clinician speech is parsed into thought units; each unit has at most one code; each volley earns each code once. Prefer fewer parses when uncertain. | **Match:** `src/onolys_miti/data/prompts/code_system.md:8–20`; `src/onolys_miti/score.py:31–52`; pack rules at `src/onolys_miti/data/pack.yaml:257–264`. Utterance splitting is model judgment. The deterministic one-code check compares identical turn/start/end spans; it does not adjudicate every possible semantic overlap. |
| Facilitative client input | E.1 p.13, E.3 pp.15–16: facilitative client input does not interrupt the clinician volley. An answer to a direct question or reflection may justify parsing; prefer fewer parses. | **Fixed here, approximation:** `src/onolys_miti/prepare.py:113–145,172–208`; `pack.yaml:277–282`. Input shorter than 3 whitespace words, or 6 non-space characters for predominantly Thai/CJK/Japanese letters, does not break unless the preceding clinician turn passes the question heuristic. Exactly 3 words or 6 characters breaks. The last `?`, `？` or `؟` may have a tail of at most 3 words / 6 characters after closing punctuation is stripped. This approximates meaning; short substantive responses can be merged, punctuation-free questions missed, and short statement tails misread. Answers to reflections have no special detector. The manual's three-word facilitative example is therefore not universally reproduced. |
| Reflection slot | E.1 p.13; E.4.e p.22: one reflection per volley; any complex reflection takes precedence over simple reflections. | **Match:** `pack.yaml:265–269`; `score.py:55–69` down-counts SR as `superseded_by_cr`. The simple/complex decision remains semantic. |
| Persuasion slot and winner | E.1 p.13: one persuasion family slot; E.4.c p.20: when both occur within one utterance, use Persuade with Permission. | **Fixed here:** `pack.yaml:270–275`, `score.py:55–69`; prompt `code_system.md:22–25`. Permission wins and Persuade becomes `superseded_by_persuade_permission`, excluded from Total MINA. **Approximation:** extending that winner across distinct utterances in a volley is the approved engineering choice; p.20 specifies the winner within an utterance only. |
| Question | E.4.d p.20: all question types share one code and only one is counted per volley. | **Match:** `pack.yaml:158–167,261–264`. No open/closed subcodes. |
| MI-adherent distinctions and Confront | E.4.f–h pp.24–29; E.4.i pp.30–31: MI-adherent hierarchy, specificity for Affirm, and Confront precedence over Question/Persuade. | **Match in definitions/prompt:** `pack.yaml:199–253`, `code_system.md:27–30`. These decisions are prompted; there is no deterministic semantic trumping classifier. The scorer enforces the configured per-code limits and exclusive families only. |

Ten behavior labels fit **eight family slots** (p.13 list continues with Confront on p.14): GI; Persuade **or** Persuade with Permission; Question; SR **or** CR; Affirm; Seeking Collaboration; Emphasizing Autonomy; Confront. Each family can contribute at most one count per volley. The two exclusive groups plus once-per-code limit enforce this maximum; eight is a family limit, not eight distinct available labels. `tests/test_score.py` checks the maximum and persuasion order cases.

## Permission, globals and evidence

| Rule | Manual provision | Implementation and status |
|---|---|---|
| Permission timing and context | E.4.c pp.18–19: permission may precede, accompany or follow persuasion; it can persist for minutes, subject to topic/stance/content changes. | **Match in definition:** `pack.yaml:136–155`. **Approximation added here:** `prepare.py:148–169,191–198` supplies up to four preceding client turns within 150 words / 300 spaceless characters plus the previous clinician volley's last 100 whitespace words. Oldest whole client turns are dropped first; an oversized newest turn is truncated. Snapshots precede the volley's first clinician turn and cross batch boundaries; not every in-volley facilitative interjection is newly rendered as context. Bounded history cannot guarantee recognition of permission several minutes away or after the current batch. |
| Code only current clinician speech | E.1 p.13 describes clinician behavior counts. Traceability is also a governing project requirement. | **Fixed here, engineering guard:** `code_system.md:8–15`; `src/onolys_miti/code_pass.py:180–230,269–279`. Context has text only. A quote found only there is dropped as `context_quote`, excluded from both numerator and denominator of the retry drop rate. Evidence must locate inside this volley's clinician turns. This is not a general semantic detector of copied context that also appears in the current text. |
| Four global scales, 1–5, holistic judgment | C p.3; D p.4: four globals, midpoint starting point, move according to evidence; generally withhold 5 with prominent poor practice. Anchors pp.5–12. | **Match:** `pack.yaml:25–101`; `globals_system.md:6–26`. **Fixed here:** `src/onolys_miti/globals_pass.py:173–205` preserves the proposed score with fewer than two located quotes, including zero; it no longer mechanically resets to 3 or emits source `default`. |
| Low scores and absent client language | CCT p.5: lack of client change talk does not itself penalize clinician effort. SST p.7 and FAQ 6 p.38: high SST can occur with no sustain talk. | **Fixed here / match in prompt:** `globals_system.md:10,18–22`; `tests/test_globals_pass.py` checks thin evidence, scores away from 3, and SST 5 without quotes. The model may still choose 3 when the transcript lacks support; removing the software reset does not remove that instruction. |
| Evidence quantity and caps | D p.4 gives holistic anchors, not a mandatory quote count. | **Approximation:** two located quotes is an informational diagnostic (`globals_pass.py:180–190`), not a manual scoring threshold. Invalid citations are dropped (`:140–160`). The existing deterministic poor-practice cap of 4 remains when a poor-practice quote locates (`:163–170,191–202`); converting the manual's general caution about 5 to a hard cap is an engineering restriction. Empty evidence is allowed, so preserving a score is not proof it is adequately grounded. |

## Speech left uncoded

**Match in prompt, not an exhaustive semantic validator.** Section F **p.32** lists structuring, greetings, facilitative comments, previous-session material, incomplete thoughts and off-topic speech. Related provisions: structuring is not GI (p.16); a question setup is not a separate reflection (p.23); generic praise/support is not Affirm (pp.25–26); non-persuasive self-disclosure may be uncoded (p.15 example). See `code_system.md:31–38` and `pack.yaml:108–114,166–167,203–212`. The manual is not exhaustive: uncoded speech is valid, not automatically a missing behavior code.

**Engineering visibility, fixed here:** `src/onolys_miti/coverage.py:24–53` measures uncovered whitespace words, with overlapping spans counted once and uncoded/down-counted spans included. `code_pass.py:357–365` emits informational `coverage_gap` only for at least 40 clinician words with no located utterance; partial coverage alone does not trigger that warning. Coverage never independently retries or fails a pass. It neither mandates coding every word nor establishes clinical or coding accuracy.

## Summary formulas and segment limits

**Match:** manual H pp.32–33; formulas in `pack.yaml:284–314`, evaluated by `score.py:136–164`:

| Summary | Formula |
|---|---|
| Technical | (CCT + SST) / 2 |
| Relational | (Partnership + Empathy) / 2 |
| Complex-reflection fraction | CR / (SR + CR), displayed as a percentage |
| Reflection-to-question ratio | (SR + CR) / Question |
| Total MI-adherent | Seeking Collaboration + Affirm + Emphasizing Autonomy |
| Total MI non-adherent | Confront + Persuade (excludes permission) |

Division by zero yields null, an engineering representation of an undefined ratio. Manual I p.33 gives suggested reference levels, with caveats about their evidence, and no MIA/MINA thresholds; the pack leaves those absent. These are not a clinical verdict.

Page corrections: the not-coded list and segment-length caution are F/G **p.32**, not pp.14–15. Typical 20-minute sampling is discussed on p.3; shorter-than-10-minute global difficulty is FAQ 1 p.37. G p.32 permits longer segments with caution. The project's 25-minute / 6,000-word cap, minimum turn counts, and required narrower selection beyond the cap are engineering policy, not MITI requirements (`prepare.py:218–279`, `pack.yaml:316–323`; [mission](../../../mission.md)).

See [measurement summary](measurements/summary.md) for exact snapshots and verification: final audit matches step 5, regeneration is a no-op, and two builder-fixture assertions remain pending repair (581 passed, 2 failed, 3 live cases deselected). Tests and synthetic response replay support deterministic alignment and non-regression only; independently human-coded sessions would be needed to assess accuracy.
