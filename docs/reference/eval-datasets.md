# Evaluation datasets

Metadata, scripts and manifests live in `eval/datasets/<id>/`. The repository is public: dataset content (transcripts, codes, PDFs, CSVs) is never committed. `onolys-eval fetch`, `convert` and `upload` keep it in a private cache outside git and in the private `onolys-eval-data-staging` bucket (`datasets/<id>/<session>/{transcript,gold}.json`, plus the raw coded/uncoded PDFs for PDF datasets). Manifest fields are described in [eval-site.md](eval-site.md#dataset-manifest-original-source-fields). Audio and video are never stored; we keep `transcript.v1` and `gold.v1` only.

Terms: unless noted, reuse terms are not separately confirmed and every dataset is for internal evaluation only. Change goals marked "curated" were written from the transcript and await owner review.

## casaa-miti421-video2013

- Source: CASAA "Helping People Change" 2013 video series, coded and uncoded transcript PDFs from <https://casaa.unm.edu/tools/miti.html>.
- Original media: video (ordered separately; not linked on the page) and transcript. Transcript origin: human.
- Labels: MITI 4.2.1 behavior counts and 4 global ratings, parsed from line-coded PDFs.
- Mapping: PDF code cell to gold count ids (GI, Persuade, Persuade with permission, Q, SR, CR, AF, Seek, Emphasize, Confront); counts only for clinician rows; globals from the printed ratings. Metadata overrides fix observed misprints.
- Overlaps: none recorded. Terms: reuse confirmed OK by the owner.

## casaa-miti-practice

- Source: the 12 CASAA MITI coding-practice role-plays on <https://casaa.unm.edu/tools/miti.html>. Base URL `https://casaa.unm.edu/assets/`.
  - Manuel #1 to #5 (`manuel-1` to `manuel-5`): `docs/session{N}1.pdf` (uncoded), `docs/session{N}miti.pdf` (coded), audio `files/session{N}-1.mp3`.
  - `have-you-ever-been-a-smoker`, `hawaii-every-month`, `i-guess-i-dont-have-a-choice`, `maybe-hell-take-my-kids`, `should-i-really-be-honest`, `now-i-only-wear-yoga-pants`: `docs/<slug>-uncoded-transcript.pdf`, `docs/<slug>-coded-transcript.pdf`, audio `files/<slug>.mp3`.
  - `emmys-first-encounter`: same PDF pattern; original media is the YouTube video <https://www.youtube.com/watch?v=P3JUXQ4kkHs> (manifest per-session `source_media: [video, transcript]`).
  - All URLs were checked to resolve on 2026-11-24.
- Original media: audio (video for Emmy) and transcript. Role-plays with actors, not real clients. Transcript origin: human.
- Label scheme: the coded PDFs are headed "MITI 4" / "Miti 4 Coding Training Series" and print no minor version. The manifest therefore uses `miti_version: "4.0"` with `label_scheme: "MITI 4 (minor version not stated in PDFs)"`. Owner to confirm whether 4.2 or 4.2.1 is intended.
- Labels present in all 12 sessions: the 10 behavior counts (clinician rows, integers, 0 when absent) and all 4 globals (CCT, SST, PAR, EMP; Emmy prints CULTIVATING/SOFTENING/PARTNERSHIP/EMPATHY). No partial gold was needed.
- Mapping and conversion rules: same converter as the 2013 series. Code cells in these PDFs carry free-text explanations under the code, so the explanation is not parsed; each session has an `overrides/<session>.yaml` listing the codes read from the printed code (reviewed row by row). Specific rules: `PWP` is Persuade with permission; `AFF` is Affirm; `EMP` (Emmy) is Emphasize; `SAME` (Emmy) is the last code of the preceding provider utterance; parenthetical "considered but not coded" notes never add a code; `NC` and "Structure not coded" are no code. Where the coded PDF carries inline annotations such as "(GI)" or " / " segment markers, the transcript text is taken from the uncoded PDF (`uncoded_text_turn_ids`).
- Source quirks handled: `have-you-ever-been-a-smoker` and `maybe-hell-take-my-kids` print utterance 25 as a second 22 in both PDFs (source-number override); `should-i-really-be-honest` prints utterance 2 as `Q` in the coded PDF (`number_aliases`).
- Known gaps: audio files are not stored. Emmy `t99` follows a code cell ending in a dangling `;`, so its `SAME` code (Seek) is ambiguous. Change goals are curated (owner review pending). Printed per-code totals do not exist in these PDFs, so there is no total cross-check.
- Overlaps: none. Terms: public CASAA training materials; reuse terms not separately confirmed.

## mi-tags-sample

- Source: public sample of MI-TAGS, <https://github.com/Advanced-Reality-Lab/MI-TAGS>: `sample_global_mitis.csv` and `sample_utterances.csv` (raw.githubusercontent.com `main`). Paper: Cohen et al., LREC-COLING 2024, <https://aclanthology.org/2024.lrec-main.1017/>.
- Original media: demonstration videos from public sources (per the paper abstract) and transcript. How the transcripts were made is not stated in the README or abstract, so `transcript_origin` is omitted.
- Label scheme: MITI 4.2 therapist behavior codes and 4 global scores (plus CLEAR 1.0 client tags, which we ignore).
- Files: `sample_global_mitis.csv` holds 2 complete sessions (`Type 1 Diabetes Counseling Video`, annotator A3, 98 turns; `The Ineffective Physician_ Non-Motivational Approach`, annotator A2, 24 turns) with `Tagged Text` (`T: [Code] text` per turn), `Only Text`, `Only Tags`, and Empathy, SofteningSustainTalk, CultivatingChangeTalk, Partnership scores. `sample_utterances.csv` holds 10 isolated utterances from 10 other videos (columns `id`, `Video Title`, `Turn`, `Speaker`, `Text`, `Code`, `Annotator`, `Normalized Turn`); they are not sessions, so the converter reports and skips them.
- Mapping (`onolys_eval/mitags.py`): Giving Information to `gi`; Persuade to `persuade`; Persuade with Permission to `persuade_permission`; Question to `question`; Simple Reflection to `sr`; Complex Reflection to `cr`; Affirm to `affirm`; Seeking/Seek Collaboration to `seek_collab`; Emphasize/Emphasizing Autonomy to `emphasize_autonomy`; Confront to `confront`. `Structure Statement` is not counted (the Onolys pack does not code structuring statements, so GI counts may be lower than a reader of the MITI manual expects). Client tags (Neutral, Change Talk, Counter-Change Talk) are ignored. Unknown tags are parse warnings and block upload. Globals map Empathy, SofteningSustainTalk (SST), CultivatingChangeTalk (CCT), Partnership.
- Partial gold: `gi`, `persuade`, `question`, `sr`, `cr`, `affirm`, `confront` are always integers (0 when absent). `persuade_permission`, `seek_collab` and `emphasize_autonomy` do not occur in the sample tag vocabulary, so they are `null` (not labeled) unless a session contains such a tag. Summaries are omitted.
- Known gaps: 2 sessions only; one annotator per session; change goals curated (owner review pending).
- Overlaps: the full MI-TAGS set reportedly includes 140 HLQC and 8 CASAA 2013 transcripts. Neither public sample session matches a CASAA series title; the manifest records the possible overlap with `casaa-miti421-video2013` as a note.
- Terms: the GitHub repository declares no license; the full set requires an access request. Internal evaluation use only; confirm before any redistribution.

## annomi

- Source: AnnoMI, <https://github.com/uccollab/AnnoMI>, file `AnnoMI-full.csv` (raw.githubusercontent.com `main`). Papers: Wu et al., ICASSP 2022; Future Internet 15(3):110, 2023 (<https://www.mdpi.com/1999-5903/15/3/110>; the publisher page returned HTTP 403 to our fetcher, so statements below come from the repo README and CSV).
- Size: 133 transcripts (110 high, 23 low quality), 13,551 rows = 9,699 utterances; one session per `transcript_id` (`transcript-<id>`).
- Original media: public YouTube (and some Vimeo) MI demonstration videos plus transcript. The per-session YouTube/Vimeo URL is in the manifest `notes`. The README calls the transcripts "faithfully transcribed"; the paper was not reachable, so `transcript_origin: human` rests on that wording.
- Columns used: `transcript_id`, `mi_quality`, `video_title`, `video_url`, `topic`, `utterance_id` (order), `interlocutor` (therapist/client), `utterance_text`, `annotator_id`, `therapist_input_exists/subtype`, `reflection_exists/subtype`, `question_exists/subtype`. The change goal is the `topic` field (`change_goal_source: header`).
- Annotators: 126 transcripts have one annotator. 7 (ids 7, 27, 55, 56, 66, 109, 130) were annotated by all ten; `AnnoMI-simple.csv` collapses them by majority vote. We apply the same idea to every code: a code counts only when a strict majority of that utterance's annotators gave it (ties are not counted).
- Mapping (`onolys_eval/annomi.py`): `question_exists` (open or closed) to `question`; reflection subtype simple to `sr`, complex to `cr`; therapist input subtype `information` to `gi`. An utterance can carry several codes. Counts are per utterance, so a long utterance with two reflections counts once.
- Not mapped (null): `persuade`, `persuade_permission` (input subtypes advice, options and negotiation are not cleanly Persuade versus Persuade with permission), `affirm`, `seek_collab`, `emphasize_autonomy`, `confront`. Client talk types (change, neutral, sustain) are ignored. No globals, no summaries.
- Quality: `quality_label` high/low from `mi_quality`. `label_scheme`: "AnnoMI codes mapped to MITI counts (partial)"; `miti_version: null`.
- Known gaps: one transcript (`transcript-121`, 598 utterances, 7,347 words) exceeds the engine's 6,000-word coded cap, so its manifest `coded_span` is the turn range 0 to 470 and counts cover only that span. Timestamps are not stored in `transcript.v1`. Because the labels are partial, comparisons only cover the four mapped counts.
- Overlaps: none recorded. The AutoMISC repo ships automated MISC codes for AnnoMI; those are excluded (see automisc-human).
- Terms: the repo declares no license and the README has no reuse statement. Internal evaluation use only; confirm before any redistribution.

## hlqc

- Source: HLQC (High and Low Quality Counseling), Perez-Rosas et al., ACL 2019 (<https://aclanthology.org/P19-1088/>). Archive: <https://web.eecs.umich.edu/~mihalcea/downloads/HighLowQualityCounseling.zip> (`labels.csv` plus `transcripts/<id>` text files; a `__MACOSX` folder is ignored).
- Size: `labels.csv` lists 259 ids (155 high, 104 low) but the archive holds 258 transcript files (154 high, 104 low). `high_022` has a label and no transcript file, so it is not included. Session ids are the archive ids with `-` for `_` (`high-001`, `low-104`).
- Original media: counseling videos plus transcript. Transcript origin: automatic captions. The archive has no timestamps.
- Labels: session `quality_label` (high/low) only. The archive contains no turn-level codes (no questions or reflections), so all counts are null, there are no globals or summaries, `miti_version: null` and `label_scheme` is "Session quality label (high/low) only".
- Speakers: every transcript marks speakers as `T:` (therapist, role clinician) or `C:` (client). A few lines use variants (`T: <TAB>`, `C<TAB>`, and `high_140` uses `T: text` with a space); these are accepted. Lines with no speaker tag (caption wraps; `high-102`, `high-104`, `high-135`, `low-006`, ...) are appended to the previous turn and reported by `convert`, never given a new speaker. No session was skipped for missing roles.
- Change goal: the source has none, so every session uses a generic curated goal ("Behavior change discussed in the session (the source does not record it)").
- Overlaps: the AutoMISC human-coded subset re-parses 10 HLQC conversations (`automisc-human`); the full MI-TAGS set reportedly includes 140 HLQC transcripts (not in the public sample).
- Terms: public download from the authors' page with no stated license; internal evaluation use only.

## automisc-human

- Source: AutoMISC repo <https://github.com/cimhasgithub/AutoMISC> (`archive/refs/heads/main.zip`). Paper: Mahmood et al., NLP4Health 2025, <https://aclanthology.org/2025.nlpai4health-main.4/>. Only the two human-annotated files under `data/manual/` are read: `HLQC_balanced_manual.csv` and `MIV6.3A_manual.csv`. The repo's automated (LLM) codes (`*_auto` columns, `data/parsed/`, `data/*.csv`, the `AnnoMI` files) are never used.
- Sessions (20): 10 HLQC conversations (`hlqc-high-001`, `hlqc-high-099`, `hlqc-high-117`, `hlqc-high-121`, `hlqc-high-127`, `hlqc-low-001`, `hlqc-low-026`, `hlqc-low-031`, `hlqc-low-033`, `hlqc-low-080`; 1,925 utterances, the paper says 1,924) and 10 smoking-cessation study conversations (`smoking-<conv_id>`; 821 utterances, 580 counsellor and 241 client, consensus labels from 4 annotators per the paper). Every conversation is coded in full (utterance indexes run contiguously from 0), so counts cover the whole session, `coded_span` is null, and there are no coverage warnings.
- Original media: HLQC sessions are counseling videos (automatic captions, see `hlqc`); the smoking sessions are text chats from a chatbot study (counsellor is a chatbot per the paper's "chatbot study"; client is a human smoker). Dataset-level `source_media` is `[transcript]` with a per-session `[video, transcript]` override for HLQC; `transcript_origin` is omitted because it differs by session.
- Turns: the coded utterances (a volley is split into utterances). Speakers `counsellor` / `client` map to roles clinician / client. Gold `utterance_codes` list the mapped MITI code per clinician utterance.
- Mapping (`onolys_eval/automisc.py`), using the repo's `t2_label_GT` (MISC 2.5 tier 2) code set `CR AF SU RF EC SR ADP RCP GI ADW CO DI RCW WA OQ CQ FA FI ST`:

| MISC 2.5 code | Gold count |
|---|---|
| OQ (open question), CQ (closed question) | `question` |
| SR (simple reflection) | `sr` |
| CR (complex reflection) | `cr` |
| AF (affirm) | `affirm` |
| GI (give information) | `gi` |
| ADP (advise with permission), RCP (raise concern with permission) | `persuade_permission` |
| ADW (advise without permission), RCW (raise concern without permission) | `persuade` |
| EC (emphasize control) | `emphasize_autonomy` |
| CO (confront) | `confront` |
| FI, FA, ST, SU, RF, WA, DI | not counted |

- Not counted: FI (filler), FA (facilitate), ST (structure), SU (support), RF (reframe), WA (warn), DI (direct). MISC has no Seek Collaboration, so `seek_collab` is `null`. WA and DI sit under the repo's "Imperative without permission" group; whether MITI Persuade should include them is not settled here, so `persuade` is a lower bound. `cr` is a lower bound when RF occurs. Client codes (N, R+, C+, ...) are ignored; a client code on a counsellor turn, a counsellor code on a client turn, or an unknown code is a parse warning (none occur). The MISC code definitions come from the paper's prompt appendix (the repo has no code book).
- Labels: partial counts only (9 of 10 ids are integers, 0 when absent). No globals, no summaries. HLQC sessions also carry `quality_label` (high/low from the conversation id); smoking sessions have none. `label_scheme`: "MISC 2.5 (human) mapped to MITI counts"; `miti_version: null`.
- Overlaps: the 10 HLQC sessions are the same conversations as `hlqc` ids `high-001` etc., but AutoMISC re-parsed the transcripts into utterances, so turn text and turn count differ. No AnnoMI overlap: the manual files contain no AnnoMI sessions (AutoMISC's AnnoMI codes are automated and excluded).
- Change goal: smoking sessions "Quit smoking" (curated); HLQC sessions generic.
- Terms: no license on the repo; the paper says the code and annotated data are released without stating a data license. Internal evaluation use only; confirm before any redistribution.

## welivita-mi

- Source: Welivita & Pu, "Curating a Large-Scale Motivational Interviewing Dataset using Peer Support Forums", COLING 2022 (<https://aclanthology.org/2022.coling-1.293/>). Repo <https://github.com/anuradha1992/Motivational-Interviewing-Dataset>, file `MI Dataset.csv` (raw.githubusercontent.com `main`, 4.7 MB, one row per sentence, 20,462 rows).
- Size: 2,000 dialogues (session = one dialogue, `counsel-chat-<n>` or `red-<n>-<subreddit>`): 1,000 CounselChat threads (a poster's question answered by a professional counsellor) and 1,000 Reddit RED peer-support threads. Not Reddit only. 2 to 6 turns each, at most 1,009 words, so none needs a `coded_span`. All 2,000 have at least one labeled helper sentence, so none were skipped.
- Documents are short forum threads, not counseling sessions: the seeker (`speaker`, role client) posts once or twice and the helper (`listener`, role clinician) answers in prose, with no turn-taking rhythm. Counts are far lower than in a session and the structure differs from what the MITI pack expects; treat results as a different task.
- Original media: text only (`source_media: [transcript]`, `transcript_origin: human`).
- Labels are human: trained counsellors recruited through UpWork labelled every helper sentence (two workers per batch, judges resolved conflicts, final observed agreement 93.2%, Fleiss kappa 0.55; paper section 3.3). The CSV has no model-predicted labels. We use `final agreed label`. 450 helper sentences stayed unresolved (`-`) and are not counted. Seeker rows are `N/A` and unlabeled.
- Turns: one transcript turn per dialogue turn (its sentences joined with a space; whitespace normalised). Gold `utterance_codes` list one mapped code per labeled sentence of that turn, so a code can repeat. Counts are per sentence.
- Mapping (`onolys_eval/welivita.py`), 15-label set from the paper's Table 1:

| Welivita & Pu label | Gold count | Helper sentences |
|---|---|---|
| Open Question, Closed Question | `question` | 476 + 905 |
| Simple Reflection | `sr` | 556 |
| Complex Reflection | `cr` | 1,294 |
| Affirm | `affirm` | 945 |
| Give Information | `gi` | 4,856 |
| Advise with Permission | `persuade_permission` | 484 |
| Advise without Permission | `persuade` | 2,285 |
| Emphasize Autonomy | `emphasize_autonomy` | 253 |
| Confront | `confront` | 318 |
| Support, Direct, Warn, Self-Disclose, Other | not counted | 1,233 + 898 + 113 + 1,390 + 805 |

- Gaps: `seek_collab` is `null` (no such label). `persuade` is a lower bound because Direct and Warn are not folded in (same call as `automisc-human`; owner to confirm whether MITI Persuade should include them). Total: 12,372 mapped sentences, 4,439 labeled but not mapped, 450 unresolved. 82 dialogues have only unmapped or unresolved labels, so all their mapped counts are 0. No globals, no summaries, no quality label. `miti_version: null`; `label_scheme`: "Welivita & Pu MI labels mapped to MITI counts (partial)". The per-session manifest `notes` give the mapped / unmapped / unresolved sentence counts. Change goals are a generic "Not stated" (curated).
- Overlaps: none recorded.
- Terms: CC BY-NC-SA 3.0 (non-commercial, share-alike, attribution). Cite the paper and read its ethics section (Reddit users are anonymous; do not try to identify them). Internal non-commercial evaluation only.
- Catalog and picker with 2,000 sessions: the dataset manifest is about 0.75 MB of YAML and `GET /v1/datasets` reads and validates every manifest on each call (a failure in one gives 503 for all); `GET /v1/datasets/welivita-mi` returns 2,000 session rows and lists all 4,001 objects under the prefix. The new-run picker renders one checkbox per session with all preselected, so a whole-dataset run is 2,000 sessions: select only the sessions you want. Not exercised by us.

## phac-en

- Source: Public Health Agency of Canada, "Videos on supporting behaviour change", Motivational Interviewing series (<https://www.canada.ca/en/public-health/services/chronic-diseases/videos-on-supporting-behaviour-change.html>). Four scripted primary-care scenarios, each a page with an MP4 and an on-page transcript: `alcohol`, `eating` (unhealthy eating), `physical-inactivity`, `smoking`. Pages `.../videos-on-supporting-behaviour-change/motivational-interviewing-<alcohol|unhealthy-eating|physical-inactivity|smoking>.html`; videos `.../content/dam/phac-aspc/migration/phac-aspc/video/cd-mc/<alcohol-eng|eating-alimentation-eng|physi-eng|smoking-tabagisme-eng>.mp4` (listed in each session's manifest `notes`; not downloaded or uploaded).
- Size: 4 sessions (actors, not real patients), 15 to 50 turns each: alcohol 50, eating 19, physical-inactivity 15, smoking 34. The fetch step downloads the four HTML pages (it sends a `curl/8.5` User-Agent because canada.ca stalls the default Python one).
- Original media: video + transcript (`source_media: [video, transcript]`, `transcript_origin: human`, the page transcript is the script).
- Roles come from the printed speaker labels: `DOCTOR` is clinician, `PATIENT` is client (kept as `speaker`). Excluded and never turned into turns: the narrator intro (`DR. SELBY:` or `DR. VALLIS:`, one paragraph per page, an on-camera physician explaining the scenario), `Text on screen:` teaching cues (the 5As/5Rs stage names such as Ask, Advise, Reflect, Rewards), `( ... )` stage directions, and the production credit. Excluded per page: alcohol 20, eating 18, physical-inactivity 17, smoking 20 paragraphs. The convert report lists them by category (narrator text is only printed, never stored). They are not in `gold.parse.warnings` because the upload step refuses any gold with warnings; an unlabeled paragraph of any other kind is a real warning and blocks upload.
- Labels: none. Gold is the empty file (`counts: {}`, `globals: null`, `label_scheme: "none"`, `label_source: "no human labels"`); `miti_version: null`. The gold file is still required by upload and by the catalog (`has_gold` is true), so a run that selects the `human` engine gets an all-null gold and compares nothing. Use these for engine-only runs.
- Change goals (curated, owner review pending): alcohol "Reduce alcohol use", eating "Improve eating habits", physical-inactivity "Be more physically active", smoking "Cut back on or quit smoking" (the smoking patient is explicitly not ready to quit).
- Overlaps: `phac-fr` (same four topics in French, separately staged).
- Terms: Government of Canada terms (<https://www.canada.ca/en/transparency/terms.html>): non-commercial reuse is allowed with attribution; commercial redistribution needs written permission. Internal evaluation use only; no page text is committed.

## phac-fr

- Source: French index <https://www.canada.ca/fr/sante-publique/services/maladies-chroniques/videos-aide-changement-comportement.html>; pages `.../videos-aide-changement-comportement/entrevue-motivationnelle-<alcool|alimentation-malsaine|inactivite-physique|tabagisme>.html`; videos `...-fra.mp4` (same stems as English). Session ids match `phac-en` (`alcohol`, `eating`, `physical-inactivity`, `smoking`).
- Size: 4 sessions: alcohol 56 turns, eating 18, physical-inactivity 15, smoking 36. Excluded paragraphs: alcohol 22, eating 18, physical-inactivity 17, smoking 21 (narrator `DR SELBY` / `DR VALLIS`, `Texte à l'écran`, stage directions, credit; the French alcohol page has an extra closing `(Fondu au noir.)`).
- Roles: `MÉDECIN` clinician, `PATIENTE` client (printed labels; the French pages use the feminine form and `MÉDECIN :` has a space before the colon). Everything else as `phac-en`: no labels, empty gold, same manifest fields, same terms, `overlaps_with: phac-en`.
- Not a translation of the English script: the cast and wording differ (for example the smoking patient is male in English and female in French), so do not pair sessions as parallel text.
- Language: the manifest has a new optional dataset-level `language` (BCP-47, default `en`, so existing manifests are unchanged); `phac-fr` sets `fr` and the converter writes `transcript.language: "fr"`. The new-run picker shows `Language: fr` for non-English datasets only; `GET /v1/datasets` returns the field.
- Engine French support: no change made. The MITI engine reads `transcript.language` (`engines/miti/src/onolys_miti/run.py`), passes it to the code, globals and tips prompts ("Transcript language: fr"; quotes stay in the transcript language, rationales in English) and adds the info warning `language_not_validated` for any non-English language. French input therefore runs but its quality is not validated; the eval backend uses the session language, then the request language, then `transcript.language`.

## Gated / not added

| Dataset | Why not added | How to get it |
|---|---|---|
| MI-TAGS full set (242 transcripts) | Access-gated | Request form: <https://docs.google.com/forms/d/e/1FAIpQLSfWAFOmRcPRd0751bRdQT83Qx-vC2HCnkrwl3T4Lh7HoByr6Q/viewform> |
| BiMISC | Not public | Email the first author, x.sun2@uva.nl |
| AnnoSUM-MI | Not public | arXiv 2511.22818; ask the authors |
| MIDAS (Spanish) | Spanish; not added | arXiv 2502.08458 |
| MI-LLM (Chinese) | Data not released | None |
| CASAA MITI 3.1 archive | Skipped: old MITI version | <https://casaa.unm.edu/tools/miti.html> |
| AFDEM | Terms prohibit download | None |
