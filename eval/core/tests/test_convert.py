"""Synthetic conversion fixtures: no published session text is stored here."""
import json
from pathlib import Path

import pytest
from onolys_eval import convert
from onolys_eval.cli import main
from onolys_eval.gold import Gold
from onolys_eval.manifest import DatasetManifest
from pydantic import ValidationError
from test_contracts import manifest_data


def words(lines):
    return [{"text": text, "x0": x, "x1": x + len(text)*5, "top": y, "bottom": y+10}
            for y, cells in lines for x, text in cells]


def page(label="Emphasize Persuade with", text="Synthetic speech", number="1"):
    return words([(30, [(70, "Page header")]),
                  (75, [(70, "Utt."), (100, "I"), (125, "Content"),
                        (440, "Code"), (520, "Notes")]),
                  (110, [(70, number), (100, "I"), (125, text), (440, label)]),
                  (125, [(125, "continues"), (520, "excluded note")]),
                  (160, [(70, "CCT = 4 SST = 3 PAR = 5 EMP = 5")]),
                  (190, [(70, "Emphasize = 1")]),
                  (760, [(70, "Page footer")])])


@pytest.mark.parametrize("label,expected", [
    ("GI", ["gi"]), ("Persuade", ["persuade"]),
    ("Persuade / with", ["persuade_permission"]),
    ("Emphasize / Persuade with", ["emphasize_autonomy", "persuade_permission"]),
    ("AF / Q", ["affirm", "question"]), ("Af", ["affirm"]),
    ("Q", ["question"]), ("SR", ["sr"]), ("CR", ["cr"]),
    ("Seek", ["seek_collab"]), ("Confront", ["confront"]),
    ("NC", []), ("NOT CODED", []), ("", []),
])
def test_labels(label, expected):
    assert convert.parse_codes(label) == (expected, [])


def test_word_positions_headers_notes_continuations_and_globals():
    parsed = convert.parse_pages([(page(), 792)], code_header="Code")
    assert parsed.rows[0].text == "Synthetic speech continues"
    assert parsed.rows[0].speaker == "I"
    assert parsed.rows[0].codes == ["emphasize_autonomy", "persuade_permission"]
    assert parsed.globals == {"cct": 4, "sst": 3, "partnership": 5, "empathy": 5}
    assert parsed.printed_counts == {"emphasize_autonomy": 1}


def test_wraps_codes_and_text_across_pages_and_headerless_settings():
    first = words([(80, [(70, "1"), (100, "I"), (125, "First"), (440, "Persuade")])])
    second = words([(80, [(125, "second"), (440, "with")]),
                    (100, [(70, "2"), (100, "C"), (125, "Reply")])])
    parsed = convert.parse_pages([(first, 792), (second, 792)], code_header=None,
                                 layout={"number_x": 70, "speaker_x": 100,
                                         "text_x": 125, "code_x": 440})
    assert parsed.rows[0].text == "First second"
    assert parsed.rows[0].codes == ["persuade_permission"]
    assert parsed.rows[1].speaker == "C"


def make_result(coded=None, uncoded=None, overrides=None):
    manifest = DatasetManifest.model_validate(manifest_data())
    coded = coded or convert.parse_pages([(page(), 792)], code_header="Code")
    uncoded = uncoded or coded
    return convert.build_session(manifest, manifest.sessions[0], coded, uncoded,
                                 {"sha256": "a"*64, "retrieved_at": "2026-11-23T00:00:00Z"},
                                 overrides)


def test_build_typed_gold_roles_summaries_and_span():
    transcript, gold, warnings = make_result()
    assert warnings == []
    assert transcript["turns"][0] == {"id": "t1", "speaker": "I", "role": "clinician",
                                       "text": "Synthetic speech continues"}
    assert gold.counts["persuade_permission"] == 1
    assert gold.summaries.total_mia == 1
    assert gold.parse.method == "auto"
    Gold.model_validate_json(gold.model_dump_json(by_alias=True))


@pytest.mark.parametrize("kind", ["unknown-code", "empty-row", "noncontiguous-numbers",
                                   "globals-missing", "globals-out-of-range",
                                   "printed-count-mismatch", "text-mismatch"])
def test_every_self_check(kind):
    coded = convert.parse_pages([(page(), 792)], code_header="Code")
    uncoded = convert.parse_pages([(page(), 792)], code_header="Code")
    if kind == "unknown-code":
        coded.rows[0].unknown_codes = ["Mystery"]
    elif kind == "empty-row":
        coded.rows[0].text = ""
    elif kind == "noncontiguous-numbers":
        coded.rows[0].number = 2
    elif kind == "globals-missing":
        del coded.globals["cct"]
    elif kind == "globals-out-of-range":
        coded.globals["cct"] = 7
    elif kind == "printed-count-mismatch":
        coded.printed_counts["gi"] = 4
    else:
        uncoded.rows[0].text = "Different source"
    _, gold, warnings = make_result(coded, uncoded)
    assert any(w.startswith(kind + ":") for w in warnings)
    if kind in {"globals-missing", "globals-out-of-range"}:
        assert gold is None  # never fabricate ratings even with --allow-warnings


def test_overrides_fix_codes_globals_counts_and_acknowledge_only_reviewed_text():
    coded = convert.parse_pages([(page(label="Mystery"), 792)], code_header="Code")
    coded.globals["cct"] = 8
    uncoded = convert.parse_pages([(page(text="Different source"), 792)], code_header="Code")
    override = {"utterance_codes": [{"turn_id": "t1", "codes": ["emphasize_autonomy"]}],
                "globals": {"cct": 4}, "reviewed_utterance_ids": ["t1"]}
    transcript, gold, warnings = make_result(coded, uncoded, override)
    assert warnings == []
    assert gold.parse.method == "auto+override"
    assert transcript["turns"][0]["text"] == "Synthetic speech continues"
    with pytest.raises(ValidationError):
        make_result(overrides={"text": "Forbidden"})
    with pytest.raises(ValueError, match="Unknown override"):
        make_result(overrides={"reviewed_utterance_ids": ["t99"]})


def write_pdf(path, body):
    """Tiny real text PDF, generated without a fixture or extra dependency."""
    stream = 'BT /F1 10 Tf ' + ' '.join(f'1 0 0 1 {x} {792-y} Tm ({text}) Tj'
                                      for y, cells in body for x, text in cells) + ' ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               f'<< /Length {len(stream)} >>\nstream\n{stream}\nendstream'.encode()]
    data = b'%PDF-1.4\n'; offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data)); data += f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref = len(data); data += b'xref\n0 6\n0000000000 65535 f \n'
    data += b''.join(f'{o:010d} 00000 n \n'.encode() for o in offsets[1:])
    data += f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
    path.write_bytes(data)


def test_real_pdf_io_and_cli_warning_exit_flags(tmp_path, monkeypatch, capsys):
    import yaml
    manifest = DatasetManifest.model_validate(manifest_data())
    manifest_path = tmp_path / 'manifest.yaml'
    manifest_path.write_text(yaml.safe_dump(manifest_data()))
    monkeypatch.setattr(convert, "manifest_path_for", lambda _: manifest_path)
    raw = tmp_path / 'cache/synthetic/raw'; (raw/'one').mkdir(parents=True)
    body = [(75, [(70,'Utt.'),(100,'I'),(125,'Content'),(440,'Code')]),
            (110, [(70,'1'),(100,'I'),(125,'Synthetic speech'),(440,'Unknown')]),
            (160, [(70,'CCT = 4 SST = 3 PAR = 5 EMP = 5')])]
    for name in ('coded', 'uncoded'):
        write_pdf(raw/'one'/f'{name}.pdf', body)
    (raw/'fetch.json').write_text(json.dumps({'dataset_id':'synthetic','files':{
        'one/coded.pdf':{'sha256':'a'*64,'retrieved_at':'2026-11-23T00:00:00Z'}}}))
    args = ['convert','synthetic','--cache',str(tmp_path/'cache'),'--session','one','--dump']
    assert main(args) == 1
    assert 'unknown-code' in capsys.readouterr().out
    assert main(args+['--allow-warnings']) == 0
    out = tmp_path/'cache/synthetic/one'
    assert Gold.model_validate_json((out/'gold.json').read_text()).parse.warnings
    assert json.loads((out/'transcript.json').read_text())['turns'][0]['text'] == 'Synthetic speech'
    assert len(convert.read_pdf(raw/'one/coded.pdf', manifest.sessions[0]).rows) == 1
    with pytest.raises(SystemExit):
        main(['convert','synthetic','--cache',str(Path(__file__).parent)])


def test_reviewed_ids_never_suppress_other_warnings_and_override_rejects_notes():
    coded = convert.parse_pages([(page(label="Unknown", number="3"), 792)], code_header="Code")
    _, _, warnings = make_result(coded, overrides={"reviewed_utterance_ids": ["t3"]})
    assert any(w.startswith("unknown-code:") for w in warnings)
    assert any(w.startswith("noncontiguous-numbers:") for w in warnings)
    with pytest.raises(ValidationError):
        make_result(overrides={"utterance_codes": [{"turn_id":"t1", "codes":[], "note":"text"}]})


def test_client_codes_excluded_and_zero_based_half_open_span():
    manifest = manifest_data()
    manifest['sessions'][0]['coded_span'] = {'start_turn':1, 'end_turn':2}
    manifest = DatasetManifest.model_validate(manifest)
    doc = convert.ParsedDocument(
        rows=[convert.ParsedRow(1,'I','First', codes=['gi']),
              convert.ParsedRow(2,'I','Second', codes=['question']),
              convert.ParsedRow(3,'C','Third', codes=['gi'])],
        globals=dict.fromkeys(('cct','sst','partnership','empathy'),3))
    transcript, gold, warnings = convert.build_session(manifest, manifest.sessions[0],doc,doc,
        {'sha256':'a'*64,'retrieved_at':'2026-11-23T00:00:00Z'})
    assert not warnings
    assert gold.counts['gi'] == 0 and gold.counts['question'] == 1
    assert gold.coded_span.model_dump() == {'start_turn':1, 'end_turn':2}
    assert transcript['turns'][2]['role'] == 'client'


def test_multiword_header_and_per_pdf_margins():
    data = words([(20, [(40,'Utt.'),(65,'I'),(90,'Content'),(400,'Final'),(425,'Code')]),
                  (40, [(40,'1'),(65,'I'),(90,'Synthetic'),(400,'Q')])])
    doc = convert.parse_pages([(data,792)],code_header='Final Code',
                              layout={'header_bottom':0.,'number_x':40.})
    assert doc.rows[0].text == 'Synthetic'
    assert doc.rows[0].codes == ['question']


def test_uncoded_extra_row_warns_and_missing_text_not_acknowledged():
    coded = convert.parse_pages([(page(),792)], code_header='Code')
    uncoded = convert.parse_pages([(page(),792)], code_header='Code')
    uncoded.rows.append(convert.ParsedRow(2,'C','Additional'))
    coded.rows[0].text = ''
    _, _, warnings = make_result(coded,uncoded,{'reviewed_utterance_ids':['t1']})
    assert 'empty-row: t1' in warnings
    assert 'text-mismatch: t2: missing from coded PDF' in warnings


def test_ordinary_content_notes_and_code_words_never_change_columns():
    source = page(label='Q')
    source += words([(140, [(125,'Content'),(170,'notes'),(200,'code')])])
    doc = convert.parse_pages([(source,792)],code_header='Code')
    assert doc.rows[0].text.endswith('Content notes code')
    assert doc.rows[0].codes == ['question']


def test_cli_applies_metadata_only_override_and_never_guesses_missing_globals(tmp_path, monkeypatch):
    import yaml
    manifest_path = tmp_path/'manifest.yaml'
    manifest_path.write_text(yaml.safe_dump(manifest_data()))
    monkeypatch.setattr(convert,'manifest_path_for',lambda _: manifest_path)
    cache = tmp_path/'cache'
    raw = cache/'synthetic/raw'
    (raw/'one').mkdir(parents=True)
    body = [(75, [(70,'Utt.'),(100,'I'),(125,'Content'),(440,'Code')]),
            (110, [(70,'1'),(100,'I'),(125,'Synthetic speech'),(440,'Mystery')]),
            (160, [(70,'CCT = 4 SST = 3 PAR = 5')])]
    for name in ('coded','uncoded'):
        content = body if name == 'coded' else [(y, [(x,t) for x,t in cells if x < 440]) for y,cells in body]
        write_pdf(raw/'one'/f'{name}.pdf',content)
    (raw/'fetch.json').write_text(json.dumps({'dataset_id':'synthetic','files':{
        'one/coded.pdf':{'sha256':'a'*64,'retrieved_at':'2026-11-23T00:00:00Z'}}}))
    args = ['convert','synthetic','--cache',str(cache),'--allow-warnings']
    assert main(args) == 1
    assert not (cache/'synthetic/one/gold.json').exists()
    (tmp_path/'overrides').mkdir()
    (tmp_path/'overrides/one.yaml').write_text(yaml.safe_dump({
        'utterance_codes':[{'turn_id':'t1','codes':['question']}], 'globals':{'empathy':5}}))
    assert main(args[:-1]) == 0
    gold = Gold.model_validate_json((cache/'synthetic/one/gold.json').read_text())
    assert gold.parse.method == 'auto+override'
    assert gold.parse.warnings == []
    assert gold.counts['question'] == 1
