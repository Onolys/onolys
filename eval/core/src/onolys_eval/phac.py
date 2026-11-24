"""Public Health Agency of Canada MI teaching scenarios: on-page HTML transcripts to transcript.v1.

Source: four scripted primary-care scenarios (alcohol, eating, physical inactivity, smoking) in
English and French, from the index pages under
https://www.canada.ca/en/public-health/services/chronic-diseases/videos-on-supporting-behaviour-change.html
(French: .../fr/sante-publique/services/maladies-chroniques/videos-aide-changement-comportement.html).
Each scenario page has an MP4 (not downloaded) and a ``Transcript`` / ``Transcription`` section
made of ``<p>`` paragraphs. There are no human labels, so gold is empty (counts ``{}``, globals null).

Parsing (speakers are never guessed):
- ``DOCTOR:`` / ``MEDECIN :`` paragraphs become clinician turns, ``PATIENT:`` / ``PATIENTE :``
  client turns; the printed label is kept as ``speaker``.
- Excluded, and reported (never turned into turns): ``Text on screen:`` teaching cues, ``( ... )``
  stage directions, the on-camera narrator intro (``DR. SELBY:``, ``DR. VALLIS:``, any other
  label) and the production credit.
- Any other unlabeled paragraph is a warning (it could be a missed continuation).
"""
import html
import re
from pathlib import Path

from .manifest import DatasetManifest
from .publicsets import (
    bootstrap_raw,
    convert_sessions,
    make_gold,
    read_provenance,
    source_record,
    write_manifest,
)

LABEL_SCHEME = "none"
LABEL_SOURCE = "no human labels"
_CANADA = "https://www.canada.ca"
_EN = _CANADA + "/en/public-health/services/chronic-diseases/videos-on-supporting-behaviour-change"
_FR = _CANADA + "/fr/sante-publique/services/maladies-chroniques/videos-aide-changement-comportement"
_VIDEO = _CANADA + "/content/dam/phac-aspc/migration/phac-aspc/video/cd-mc/"
# session id -> (page slug, mp4 stem, English topic, curated change goal)
_SCENARIOS = {
    "alcohol": ("alcohol", "alcohol", "Alcohol use", "Reduce alcohol use"),
    "eating": ("unhealthy-eating", "eating-alimentation", "Unhealthy eating",
               "Improve eating habits"),
    "physical-inactivity": ("physical-inactivity", "physi", "Physical inactivity",
                            "Be more physically active"),
    "smoking": ("smoking", "smoking-tabagisme", "Smoking", "Cut back on or quit smoking"),
}
_FR_SLUGS = {"alcohol": "alcool", "eating": "alimentation-malsaine",
             "physical-inactivity": "inactivite-physique", "smoking": "tabagisme"}
LANGUAGES = {
    "en": {"dataset_id": "phac-en", "base": _EN, "prefix": "motivational-interviewing-",
           "suffix": "eng", "heading": r"Transcript",
           "cue": r"text on screen", "credit": r"production of this video"},
    "fr": {"dataset_id": "phac-fr", "base": _FR, "prefix": "entrevue-motivationnelle-",
           "suffix": "fra", "heading": r"Transcription",
           "cue": r"texte à l[’']écran", "credit": r"la production de cette"},
}
_ROLES = {"DOCTOR": "clinician", "MEDECIN": "clinician", "MÉDECIN": "clinician",
          "PATIENT": "client", "PATIENTE": "client"}
_LABEL = re.compile(r"^([A-ZÀ-Ý][A-ZÀ-Ý.' -]{0,30}?)\s*:\s*(.*)$", re.DOTALL)


def page_name(language: str, session_id: str) -> str:
    cfg = LANGUAGES[language]
    slug = _SCENARIOS[session_id][0] if language == "en" else _FR_SLUGS[session_id]
    return f"{cfg['prefix']}{slug}.html"


def page_url(language: str, session_id: str) -> str:
    return f"{LANGUAGES[language]['base']}/{page_name(language, session_id)}"


def video_url(language: str, session_id: str) -> str:
    return f"{_VIDEO}{_SCENARIOS[session_id][1]}-{LANGUAGES[language]['suffix']}.mp4"


def _text(fragment: str) -> str:
    plain = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return " ".join(plain.split())


def parse_transcript(page: str, language: str):
    """Return (turns, excluded, warnings); excluded is a list of (category, text)."""
    cfg = LANGUAGES[language]
    section = re.search(rf"<h2[^>]*>\s*{cfg['heading']}[^<]*</h2>(.*?)</div>", page, re.DOTALL)
    if section is None:
        raise ValueError("No transcript section found on the page")
    turns, excluded, warnings = [], [], []
    for raw in re.findall(r"<p[^>]*>(.*?)</p>", section.group(1), re.DOTALL):
        text = _text(raw)
        if not text:
            continue
        lowered = text.lower()
        if re.match(cfg["cue"], lowered):
            excluded.append(("on-screen cue", text))
        elif text.startswith("(") and text.endswith(")"):
            excluded.append(("stage direction", text))
        elif re.match(cfg["credit"], lowered):
            excluded.append(("credit", text))
        elif match := _LABEL.match(text):
            label = " ".join(match.group(1).split()).upper()
            role = _ROLES.get(label)
            if role is None:
                excluded.append((f"narrator ({label})", text))
            elif match.group(2).strip():
                turns.append({"id": f"t{len(turns)+1}", "speaker": label, "role": role,
                              "text": match.group(2).strip()})
            else:
                warnings.append(f"empty-turn: {label}")
        else:
            warnings.append(f"unlabeled-paragraph: {text[:60]}")
    if not turns:
        raise ValueError("No speaker-labeled turns found")
    if {t["role"] for t in turns} != {"clinician", "client"}:
        raise ValueError("Transcript lacks a clinician or a client speaker")
    return turns, excluded, warnings


def build_session(dataset_id, session_id, language, turns, *, retrieved_at, sha256, coded_url):
    transcript = {"language": language, "turns": turns}
    gold = make_gold(
        dataset_id, session_id,
        source={"coded_url": coded_url, "retrieved_at": retrieved_at, "sha256": sha256},
        counts={}, utterance_codes=None, warnings=[],
        label_source=LABEL_SOURCE, label_scheme=LABEL_SCHEME)
    return transcript, gold


def _summary(excluded) -> str:
    counts = {}
    for category, _ in excluded:
        counts[category] = counts.get(category, 0) + 1
    return ", ".join(f"{n} {c}" for c, n in sorted(counts.items()))


def convert_phac_dataset(manifest: DatasetManifest, cache: Path | None = None,
                         session_id: str | None = None):
    from .fetch import default_cache, require_external_path

    cache = require_external_path(cache if cache is not None else default_cache())
    raw = cache / manifest.dataset_id / "raw"
    files = read_provenance(raw, manifest.dataset_id)
    language = manifest.language
    notes = []

    def build(session):
        name = page_name(language, session.session_id)
        turns, excluded, warnings = parse_transcript((raw / name).read_text(encoding="utf-8"),
                                                     language)
        notes.append(f"{session.session_id}: {len(turns)} turns; excluded "
                     f"{len(excluded)} non-dialogue paragraphs ({_summary(excluded)})")
        for category, text in excluded:
            if category.startswith("narrator"):
                notes.append(f"{session.session_id}: excluded {category}: {text[:80]}...")
        transcript, gold = build_session(manifest.dataset_id, session.session_id, language, turns,
                                         **source_record(files, name))
        return transcript, gold, warnings

    status, report = convert_sessions(manifest, cache, session_id, build)
    return status, notes + report


def header(language: str) -> dict:
    cfg = LANGUAGES[language]
    other = "phac-fr" if language == "en" else "phac-en"
    return {
        "dataset_id": cfg["dataset_id"],
        "title": ("PHAC primary-care MI teaching scenarios (4 videos, English)" if language == "en"
                  else "PHAC primary-care MI teaching scenarios (4 videos, French)"),
        "license_note": "Government of Canada terms (https://www.canada.ca/en/transparency/terms.html): "
                        "non-commercial reuse is allowed with attribution; commercial redistribution "
                        "needs written permission. Internal evaluation use only.",
        "source_page": cfg["base"] + ".html",
        "miti_version": None,
        "label_scheme": LABEL_SCHEME,
        "language": language,
        "source_media": ["video", "transcript"],
        "transcript_origin": "human",
        "labels_summary": "No human labels (transcript only)",
        "overlaps_with": [{"dataset_id": other,
                           "note": "The same four scenario topics in "
                                   + ("French" if language == "en" else "English")
                                   + ", but separately staged (different cast and script, e.g. "
                                     "the smoking patient is male in English and female in "
                                     "French); not a word-for-word translation."}],
        "source_format": "phac_html",
        "source_files": [page_url(language, s) for s in _SCENARIOS],
    }


def build_manifest(path: Path, language: str, cache: Path | None = None):
    cfg = LANGUAGES[language]
    files = [page_url(language, s) for s in _SCENARIOS]
    bootstrap_raw(cfg["dataset_id"], "phac_html", files, cache)
    sessions = []
    for sid, (_, _, topic, goal) in _SCENARIOS.items():
        sessions.append({
            "session_id": sid, "title": f"PHAC scenario: {topic} ({language})",
            "clinician_labels": ["DOCTOR" if language == "en" else "MÉDECIN"],
            "code_header": None, "change_goal": goal, "change_goal_source": "curated",
            "coded_span": None,
            "notes": f"scripted teaching scenario (doctor and patient actors); owner review of "
                     f"change goal pending; video {video_url(language, sid)}"})
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_manifest(path, header(language), sessions)


if __name__ == "__main__":
    import sys

    lang = sys.argv[1]
    build_manifest(Path(__file__).resolve().parents[3] / "datasets" / LANGUAGES[lang]["dataset_id"]
                   / "manifest.yaml", lang)
