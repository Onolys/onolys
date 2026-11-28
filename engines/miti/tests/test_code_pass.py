import asyncio

import pytest
from conftest import install_demo
from onolys_engine.llm import LLMBadOutput, LLMRequest, LLMResult, MetricsCollector
from onolys_engine.llm.litellm_client import LiteLLMClient
from onolys_engine.llm.routes import Route
from onolys_engine.transcript import Turn
from pydantic import ValidationError

from onolys_miti.code_pass import (
    CodePassFailed,
    build_requests_parts,
    code_pass,
    make_response_model,
)
from onolys_miti.prepare import Prepared, RoleTurn, Volley

pytestmark = pytest.mark.unit

TEXTS = {
    "t0": "First thing here. Second thing here.",
    "t1": "Alpha beta gamma. Delta epsilon zeta.",
    "t2": "Third thing here. Fourth thing here.",
}


def make_pack(tmp_path, pack_data, params=None):
    if params is not None:
        pack_data["params"] = params
    return install_demo(tmp_path / "p", pack=pack_data)


def volleys(n):
    out = []
    for i in range(n):
        t = Turn(id=f"t{i}", speaker="A", text=TEXTS["t0"], start_ms=i * 1000, end_ms=i * 1000 + 500)
        prev = Turn(id=f"p{i}", speaker="B", text="client said something")
        out.append(Volley(f"v{i + 1}", [t], {"client_turns": [prev.text]}))
    return out


def prepared(vs):
    turns = [RoleTurn(t, "subject") for v in vs for t in v.turns]
    return Prepared(turns=turns, volleys=vs)


def utt(quote, code="a", rationale="r"):
    return {"quote": quote, "code": code, "rationale": rationale}


def good(req, per_volley=None):
    """A valid response for every volley in the request: one utterance each."""
    ids = [v["volley_id"] for v in _req_volleys(req)]
    per = per_volley or (lambda vid: [utt("First thing here.")])
    return req.response_model.model_validate(
        {"volleys": [{"volley_id": vid, "utterances": per(vid)} for vid in ids]}
    )


def _req_volleys(req):
    import json

    return json.loads(req.user)["volleys"]


class FakeClient:
    def __init__(self, handler):
        self.handler = handler
        self.requests: list[LLMRequest] = []

    async def complete_json(self, req, metrics=None):
        self.requests.append(req)
        parsed = self.handler(req, len(self.requests))
        if asyncio.iscoroutine(parsed):
            parsed = await parsed
        return LLMResult(parsed=parsed, model="fake")


async def run(client, pack, vs, **kw):
    return await code_pass(client, prepared(vs), {"change_goal": "synthetic goal"}, **kw)


async def test_request_route_and_no_sampling_param(tmp_path, pack_data):
    client = FakeClient(lambda req, n: good(req))
    await run(client, make_pack(tmp_path, pack_data, {}), volleys(26))  # engine defaults
    assert [len(_req_volleys(r)) for r in client.requests] == [25, 1]
    req = client.requests[0]
    assert req.tier == "miti_code"
    assert req.temperature == LLMRequest.__dataclass_fields__["temperature"].default  # untouched
    assert req.max_tokens is None  # no pack param: the route cap applies
    assert len(req.cache_prefixes) == 2
    assert req.call_tag.startswith("miti_code")


async def test_response_model_code_enum(tmp_path, pack_data):
    model = make_response_model(["a", "b", "c"])
    ok = {"volleys": [{"volley_id": "v1", "utterances": [utt("x", "a"), utt("y", None)]}]}
    assert model.model_validate(ok)
    bad = {"volleys": [{"volley_id": "v1", "utterances": [utt("x", "zzz")]}]}
    with pytest.raises(ValidationError):
        model.model_validate(bad)


async def test_prompt_has_system_definitions_fewshot(tmp_path, pack_data):
    make_pack(tmp_path, pack_data)
    parts = build_requests_parts({"change_goal": "synthetic goal"}, language="en")
    first, second = parts.cache_prefixes
    assert "code system" in first  # code_system.md
    assert "- a (A): d" in first  # items rendered from pack.yaml
    assert "synthetic goal" in second and "en" in second
    assert "synthetic goal" not in first  # first prefix identical across runs


async def test_batch_size_honoured(tmp_path, pack_data):
    pack = make_pack(tmp_path, pack_data, {"volleys_per_call": 2, "code_max_tokens": 4000})
    client = FakeClient(lambda req, n: good(req))
    out = await run(client, pack, volleys(5))
    assert [len(_req_volleys(r)) for r in client.requests] == [2, 2, 1]
    assert [i.volley_id for i in out.instances] == ["v1", "v2", "v3", "v4", "v5"]
    assert [i.id for i in out.instances] == ["i1", "i2", "i3", "i4", "i5"]
    assert client.requests[0].max_tokens == 4000  # pack param overrides engine default


async def test_second_batch_not_started_before_first_returns(tmp_path, pack_data):
    pack = make_pack(tmp_path, pack_data, {"volleys_per_call": 1})
    gate = asyncio.Event()

    async def handler(req, n):
        if n == 1:
            await gate.wait()
        return good(req)

    client = FakeClient(handler)
    task = asyncio.create_task(run(client, pack, volleys(3)))
    for _ in range(20):
        await asyncio.sleep(0)
    assert len(client.requests) == 1  # warm call alone
    gate.set()
    out = await task
    assert len(client.requests) == 3
    assert len(out.instances) == 3


async def test_bad_output_halves_then_retries_each_half(tmp_path, pack_data):
    pack = make_pack(tmp_path, pack_data, {"volleys_per_call": 4})

    def handler(req, n):
        if n == 1:
            raise LLMBadOutput("truncated")
        return good(req)

    client = FakeClient(handler)
    out = await run(client, pack, volleys(4))
    assert [len(_req_volleys(r)) for r in client.requests] == [4, 2, 2]
    assert len(out.instances) == 4


async def test_bad_output_in_half_fails_run(tmp_path, pack_data):
    pack = make_pack(tmp_path, pack_data, {"volleys_per_call": 4})

    def handler(req, n):
        if n <= 2:
            raise LLMBadOutput("truncated")
        return good(req)

    client = FakeClient(handler)
    with pytest.raises(CodePassFailed):
        await run(client, pack, volleys(4))
    assert len(client.requests) == 2  # full, first half; no third try


async def test_single_volley_bad_output_retried_once_then_fails(tmp_path, pack_data):
    client = FakeClient(lambda req, n: (_ for _ in ()).throw(LLMBadOutput("x")))
    with pytest.raises(CodePassFailed):
        await run(client, make_pack(tmp_path, pack_data), volleys(1))
    assert len(client.requests) == 2


async def test_drop_at_20_percent_is_kept_with_warning(tmp_path, pack_data):
    text = "One aaa. Two bbb. Three ccc. Four ddd. Five eee."
    v = Volley("v1", [Turn(id="t1", speaker="A", text=text)], {})
    quotes = ["One aaa.", "Two bbb.", "Three ccc.", "Four ddd.", "not in the transcript"]
    client = FakeClient(lambda req, n: good(req, lambda vid: [utt(q) for q in quotes]))
    out = await run(client, make_pack(tmp_path, pack_data), [v])
    assert len(client.requests) == 1  # exactly 20% is not over the limit
    assert [w.code for w in out.warnings] == ["quote_not_found"]
    assert len(out.instances) == 4


async def test_drop_over_20_percent_retries_once_then_ok(tmp_path, pack_data):
    def handler(req, n):
        if n == 1:
            return good(req, lambda vid: [utt("nope one"), utt("First thing here.")])
        return good(req)

    client = FakeClient(handler)
    out = await run(client, make_pack(tmp_path, pack_data), volleys(1))
    assert len(client.requests) == 2
    assert out.warnings == []  # warnings come from the accepted attempt only
    assert len(out.instances) == 1


async def test_drop_over_20_percent_twice_fails(tmp_path, pack_data):
    client = FakeClient(lambda req, n: good(req, lambda vid: [utt("nope"), utt("First thing here.")]))
    with pytest.raises(CodePassFailed):
        await run(client, make_pack(tmp_path, pack_data), volleys(1))
    assert len(client.requests) == 2


async def test_locate_offsets_and_overlap(tmp_path, pack_data):
    v = Volley("v1", [Turn(id="t9", speaker="A", text="Alpha beta gamma. Delta epsilon zeta.",
                           start_ms=10, end_ms=20)], {})
    client = FakeClient(lambda req, n: good(req, lambda vid: [
        utt("Alpha beta gamma.", "a"),
        utt("alpha  BETA gamma.", "b"),  # same span again -> overlap
        utt("Delta epsilon zeta.", None),
        utt("Alpha beta gamma. Delta", "c"),  # earlier + overlapping -> overlap
    ]))
    # 2 of 4 dropped = 50% -> retry then fail; use a looser batch to inspect the result instead
    with pytest.raises(CodePassFailed):
        await run(client, make_pack(tmp_path, pack_data), [v])

    client = FakeClient(lambda req, n: good(req, lambda vid: [
        utt("Alpha beta gamma.", "a"),
        utt("delta  EPSILON zeta.", None),
    ]))
    out = await run(client, make_pack(tmp_path, pack_data), [v])
    first, second = out.instances
    assert (first.turn_id, first.start, first.end) == ("t9", 0, 17)
    assert first.quote == "Alpha beta gamma." and first.counted and first.code == "a"
    assert (first.start_ms, first.end_ms) == (10, 20)
    assert (second.start, second.end) == (18, 37)
    assert second.quote == "Delta epsilon zeta."  # text as in the turn, not as the model wrote it
    assert second.code is None and second.counted is False and second.uncounted_reason == "uncoded"
    assert out.coverage['covered_words'] == out.coverage['clinician_words'] == 6
    assert out.coverage['residual_words'] == 0


async def test_quote_never_crosses_turn_boundary(tmp_path, pack_data):
    v = Volley("v1", [Turn(id="t1", speaker="A", text="Alpha beta gamma."),
                      Turn(id="t2", speaker="A", text="Delta epsilon zeta.")], {})
    client = FakeClient(lambda req, n: good(req, lambda vid: [
        utt("Alpha beta gamma. Delta epsilon zeta.")]))
    with pytest.raises(CodePassFailed):  # 100% dropped, twice
        await run(client, make_pack(tmp_path, pack_data), [v])


async def test_second_turn_located_in_its_own_turn(tmp_path, pack_data):
    v = Volley("v1", [Turn(id="t1", speaker="A", text="Alpha beta gamma."),
                      Turn(id="t2", speaker="A", text="Delta epsilon zeta.")], {})
    client = FakeClient(lambda req, n: good(req, lambda vid: [
        utt("Alpha beta gamma."), utt("Delta epsilon zeta.", "b")]))
    out = await run(client, make_pack(tmp_path, pack_data), [v])
    assert [(i.turn_id, i.start, i.end) for i in out.instances] == [("t1", 0, 17), ("t2", 0, 19)]


async def test_token_params_clamped_to_route(tmp_path, pack_data):
    client = FakeClient(lambda req, n: good(req))
    await run(client, make_pack(tmp_path, pack_data), volleys(1))
    route = Route(litellm_id="x/y", max_output_tokens=3000)
    assert LiteLLMClient._limits(route, client.requests[0])[0] == 3000


async def test_metrics_passed_through(tmp_path, pack_data):
    seen = []

    class C(FakeClient):
        async def complete_json(self, req, metrics=None):
            seen.append(metrics)
            return await super().complete_json(req, metrics)

    m = MetricsCollector()
    await run(C(lambda req, n: good(req)), make_pack(tmp_path, pack_data), volleys(1), metrics=m)
    assert seen == [m]


def _resp(req, ids):
    return req.response_model.model_validate(
        {"volleys": [{"volley_id": v, "utterances": [utt("First thing here.")]} for v in ids]}
    )


@pytest.mark.parametrize(
    "ids",
    [[], ["v1", "v3"], ["v1", "v2", "v2", "v3"], ["v1", "v2", "v3", "vX"], ["v1", "v2", "vX"]],
    ids=["empty_outer", "omitted_middle", "duplicate", "unknown_extra", "unknown_replaces"],
)
async def test_incomplete_coverage_fails_run(tmp_path, pack_data, ids):
    client = FakeClient(lambda req, n: _resp(req, ids))
    with pytest.raises(CodePassFailed):
        await run(client, make_pack(tmp_path, pack_data), volleys(3))


async def test_incomplete_coverage_recovers_via_halving(tmp_path, pack_data):
    def handler(req, n):
        return _resp(req, [] if n == 1 else [v["volley_id"] for v in _req_volleys(req)])

    client = FakeClient(handler)
    out = await run(client, make_pack(tmp_path, pack_data), volleys(2))
    assert [len(_req_volleys(r)) for r in client.requests] == [2, 1, 1]
    assert len(out.instances) == 2


async def test_complete_response_and_explicit_empty_list_valid(tmp_path, pack_data):
    def handler(req, n):
        return req.response_model.model_validate({"volleys": [
            {"volley_id": "v1", "utterances": [utt("First thing here.")]},
            {"volley_id": "v2", "utterances": []},
        ]})

    out = await run(FakeClient(handler), make_pack(tmp_path, pack_data), volleys(2))
    assert [i.volley_id for i in out.instances] == ["v1"]


async def test_deadline_reaches_every_request(tmp_path, pack_data):
    client = FakeClient(lambda req, n: good(req))
    await run(client, make_pack(tmp_path, pack_data, {}), volleys(26), deadline=123.5)
    assert len(client.requests) == 2
    assert [r.deadline for r in client.requests] == [123.5, 123.5]


async def test_output_format_says_all_ids_returned_and_empty_allowed(tmp_path, pack_data):
    from onolys_miti.code_pass import _OUTPUT_FORMAT

    text = " ".join(_OUTPUT_FORMAT.split())
    assert "every volley id appears exactly once" in text
    assert "empty" in text and "allowed" in text


class StubClient(FakeClient):
    """Offline responses inspect only the rendered request, never a provider."""


def context_volleys(spec):
    from onolys_miti.prepare import build_volleys

    return build_volleys([
        RoleTurn(Turn(id=f"private-id-{i}", speaker=speaker, text=text),
                 "subject" if speaker == "A" else "other")
        for i, (speaker, text) in enumerate(spec)
    ], {})


@pytest.mark.parametrize("client_texts,expected", [
    ([f"client reply number {i}" for i in range(6)],
     [f"client reply number {i}" for i in range(2, 6)]),
    (["old " * 70, "middle " * 80, "recent " * 71], ["recent " * 71]),
    (["old reply here", " ".join(f"word{i}" for i in range(160))],
     [" ".join(f"word{i}" for i in range(10, 160))]),
    (["旧" * 160, "新" * 150], ["新" * 150]),
    (["旧回复", "新" * 310], ["新" * 300]),
])
async def test_context_client_bounds_and_text_only(tmp_path, pack_data, client_texts, expected):
    vs = context_volleys([*(('B', text) for text in client_texts), ('A', TEXTS['t0'])])
    client = StubClient(lambda req, n: good(req))
    await run(client, make_pack(tmp_path, pack_data), vs)
    rendered = _req_volleys(client.requests[0])[0]
    context = rendered["context_before"]
    assert context == {"client_turns": expected, "previous_clinician_volley": None}
    assert "previous_other_turn" not in rendered
    assert "private-id" not in str(context)
    assert all(text not in prefix for text in expected for prefix in client.requests[0].cache_prefixes)


async def test_context_previous_volley_crosses_batch_and_batches_stay_disjoint(tmp_path, pack_data):
    previous = " ".join(f"word{i}" for i in range(125))
    vs = context_volleys([('A', previous), ('B', 'yeah'), ('A', 'Last statement?'),
                          ('B', 'sure'), ('A', TEXTS['t0'])])
    client = StubClient(lambda req, n: good(req, lambda vid: [utt(
        _req_volleys(req)[0]['clinician_turns'][0]['text'])]))
    await run(client, make_pack(tmp_path, pack_data, {"volleys_per_call": 1}), vs)
    assert len(client.requests) == 2
    context = _req_volleys(client.requests[1])[0]['context_before']
    expected = " ".join((previous + " Last statement?").split()[-100:])
    assert context == {"client_turns": ['yeah', 'sure'],
                       "previous_clinician_volley": expected}
    assert 'private-id' not in str(context)
    assert client.requests[0].cache_prefixes == client.requests[1].cache_prefixes
    ids = [{t['turn_id'] for v in _req_volleys(r) for t in v['clinician_turns']}
           for r in client.requests]
    assert ids[0].isdisjoint(ids[1])


@pytest.mark.parametrize('context_source', ['client', 'clinician'])
async def test_context_only_quote_dropped_without_retry(tmp_path, pack_data, context_source):
    text = 'Permission was already granted.'
    spec = [('B', text), ('A', TEXTS['t0'])] if context_source == 'client' else [
        ('A', text + '?'), ('B', 'yes'), ('A', TEXTS['t0'])]
    vs = context_volleys(spec)
    client = StubClient(lambda req, n: good(req, lambda vid: [utt(text)]
                        if vid == vs[-1].id else []))
    out = await run(client, make_pack(tmp_path, pack_data, {"volleys_per_call": 1}), vs)
    assert len(client.requests) == len(vs)
    assert out.instances == []
    assert [w.code for w in out.warnings] == ['context_quote']


@pytest.mark.parametrize("batch_size, expected", [(1, "context_quote"), (2, "quote_not_found")])
async def test_context_quote_requires_absence_from_actual_batch(
    tmp_path, pack_data, batch_size, expected,
):
    previous = "Permission was already granted."
    current = ["One aaa.", "Two bbb.", "Three ccc.", "Four ddd."]
    vs = context_volleys([('A', previous), ('B', 'A substantive client response.'),
                          ('A', ' '.join(current))])
    client = StubClient(lambda req, n: good(req, lambda vid: [
        *(utt(text) for text in current), utt(previous),
    ] if vid == vs[-1].id else []))
    out = await run(client, make_pack(tmp_path, pack_data, {"volleys_per_call": batch_size}), vs)
    assert len(client.requests) == (2 if batch_size == 1 else 1)
    assert [w.code for w in out.warnings] == [expected]
    assert [i.quote for i in out.instances] == current
    assert {i.turn_id for i in out.instances} == {vs[-1].turns[0].id}


async def test_same_batch_context_quote_counts_toward_retry_rate(tmp_path, pack_data):
    previous = "Permission was already granted."
    vs = context_volleys([('A', previous), ('B', 'A substantive client response.'),
                          ('A', TEXTS['t0'])])
    client = StubClient(lambda req, n: good(req, lambda vid: [utt(previous)]
                        if vid == vs[-1].id else []))
    with pytest.raises(CodePassFailed):
        await run(client, make_pack(tmp_path, pack_data), vs)
    assert len(client.requests) == 2


async def test_context_guard_uses_actual_half_batch_after_bad_output(tmp_path, pack_data):
    vs = context_volleys([
        ('A', 'Permission was already granted.'), ('B', 'A substantive client response.'),
        ('A', TEXTS['t0']), ('B', 'Another substantive client response.'),
        ('A', TEXTS['t1']), ('B', 'One more substantive client response.'),
        ('A', TEXTS['t2']),
    ])
    current = ['Third thing', 'here.', 'Fourth thing', 'here.']

    def handler(req, n):
        if n == 1:
            raise LLMBadOutput('truncated')
        return good(req, lambda vid: [utt(TEXTS['t0'])] if vid == vs[2].id else [
            *(utt(text) for text in current), utt(TEXTS['t1']),
        ] if vid == vs[3].id else [])

    client = StubClient(handler)
    out = await run(client, make_pack(tmp_path, pack_data, {"volleys_per_call": 4}), vs)
    assert [len(_req_volleys(req)) for req in client.requests] == [4, 2, 2]
    # v2 is outside the actual second half; v3 is still inside it.
    assert [(w.code, w.detail) for w in out.warnings] == [
        ('context_quote', f'{vs[2].id}: utterance dropped'),
        ('quote_not_found', f'{vs[3].id}: utterance dropped'),
    ]
    assert [i.quote for i in out.instances] == current
    assert {i.turn_id for i in out.instances} == {vs[3].turns[0].id}


async def test_current_quote_wins_over_context_and_overlap_is_still_a_failure(tmp_path, pack_data):
    vs = context_volleys([('B', TEXTS['t0']), ('A', TEXTS['t0'])])
    client = StubClient(lambda req, n: good(req))
    out = await run(client, make_pack(tmp_path, pack_data), vs)
    assert len(client.requests) == 1 and len(out.instances) == 1 and out.warnings == []
    client = StubClient(lambda req, n: good(req, lambda vid: [utt('First thing here.')] * 2))
    with pytest.raises(CodePassFailed):
        await run(client, make_pack(tmp_path, pack_data), vs)
    assert len(client.requests) == 2


async def test_context_quotes_do_not_dilute_actual_quote_misses(tmp_path, pack_data):
    vs = context_volleys([('B', 'A context sentence.'), ('A', TEXTS['t0'])])

    def handler(req, n):
        if n == 1:
            return good(req, lambda vid: [utt('A context sentence.')] * 8 + [
                utt('First thing here.'), utt('An invented sentence.')])
        return good(req)

    client = StubClient(handler)
    out = await run(client, make_pack(tmp_path, pack_data), vs)
    assert len(client.requests) == 2
    assert len(out.instances) == 1 and out.warnings == []


async def test_other_volley_quote_without_own_context_is_real_miss(tmp_path, pack_data):
    vs = volleys(2)
    vs[0].turns[0].text = 'Different current evidence.'
    client = StubClient(lambda req, n: good(req))
    with pytest.raises(CodePassFailed):
        await run(client, make_pack(tmp_path, pack_data), vs)
    assert len(client.requests) == 2


def test_real_fewshots_use_context_before():
    import json

    from onolys_miti import miti

    path = miti.DATA_DIR / 'prompts/code_fewshot.json'
    examples = json.loads(path.read_text())
    assert all('context_before' in ex['input'] for ex in examples)
    assert 'previous_other_turn' not in path.read_text()


def test_coverage_partial_words_union_and_uncounted_evidence():
    from onolys_miti.coverage import coverage
    from onolys_miti.result import Instance

    vs = [Volley('v1', [Turn(id='t1', speaker='A', text='one two\tthree four')]),
          Volley('v2', [Turn(id='t2', speaker='A', text='five six')])]

    def evidence(start, end, code, reason):
        return Instance(id='', volley_id='v1', turn_id='t1', start=start, end=end,
                        quote=vs[0].turns[0].text[start:end], code=code, counted=False,
                        uncounted_reason=reason, rationale='hand evidence')

    result = coverage(vs, [evidence(1, 6, None, 'uncoded'),
                           evidence(5, 9, 'a', 'downcounted'),
                           evidence(7, 8, None, 'uncoded')])  # whitespace alone
    assert result == {
        'clinician_words': 6, 'covered_words': 3, 'residual_words': 3,
        'volleys': [
            {'volley_id': 'v1', 'clinician_words': 4, 'covered_words': 3, 'residual_words': 1},
            {'volley_id': 'v2', 'clinician_words': 2, 'covered_words': 0, 'residual_words': 2},
        ],
    }


async def test_coverage_gap_threshold_no_retry_and_uncoded_is_located(tmp_path, pack_data):
    vs = [Volley(f'v{i}', [Turn(id=f't{i}', speaker='A', text='word ' * words)])
          for i, words in enumerate([39, 40, 40], 1)]

    def handler(req, n):
        return good(req, lambda vid: [utt('word', None)] if vid == 'v3' else [])

    client = StubClient(handler)
    out = await run(client, make_pack(tmp_path, pack_data, {'volleys_per_call': 1}), vs)
    assert len(client.requests) == 3
    assert [(w.code, w.severity) for w in out.warnings] == [('coverage_gap', 'info')]
    assert 'v2' in out.warnings[0].detail
    assert out.coverage['clinician_words'] == 119
    assert out.coverage['covered_words'] == 1
    assert out.coverage['residual_words'] == 118
    assert [v['residual_words'] for v in out.coverage['volleys']] == [39, 40, 39]


async def test_coverage_uses_only_accepted_retry_and_all_clinician_turns(tmp_path, pack_data):
    v = Volley('v1', [Turn(id='t1', speaker='A', text='one two'),
                      Turn(id='t2', speaker='A', text='three ' * 38)],
               {'client_turns': ['client ' * 100]})

    def handler(req, n):
        return good(req, lambda vid: [utt('one two'), utt('invented text')]
                    if n == 1 else [])

    client = StubClient(handler)
    out = await run(client, make_pack(tmp_path, pack_data), [v])
    assert len(client.requests) == 2  # actual quote drop retries; coverage never adds a call
    assert out.instances == []
    assert [(w.code, w.severity) for w in out.warnings] == [('coverage_gap', 'info')]
    assert out.coverage['clinician_words'] == out.coverage['residual_words'] == 40
    assert out.coverage['covered_words'] == 0


async def test_empty_code_pass_has_zero_coverage(tmp_path, pack_data):
    client = StubClient(lambda req, n: good(req))
    out = await run(client, make_pack(tmp_path, pack_data), [])
    assert client.requests == [] and out.warnings == []
    assert out.coverage == {'clinician_words': 0, 'covered_words': 0,
                            'residual_words': 0, 'volleys': []}


async def test_context_only_gap_remains_info_without_retry(tmp_path, pack_data):
    v = Volley('v1', [Turn(id='t1', speaker='A', text='word ' * 40)],
               {'client_turns': ['A context sentence.']})
    client = StubClient(lambda req, n: good(req, lambda vid: [utt('A context sentence.')]))
    out = await run(client, make_pack(tmp_path, pack_data), [v])
    assert len(client.requests) == 1
    assert [(w.code, w.severity) for w in out.warnings] == [
        ('context_quote', 'warning'), ('coverage_gap', 'info')]
    assert out.coverage['residual_words'] == 40


async def test_overlong_rationale_is_truncated_with_an_info_warning(tmp_path, pack_data):
    client = FakeClient(lambda req, n: good(req, lambda vid: [utt("First thing here.", "a", "word " * 100)]))
    out = await run(client, make_pack(tmp_path, pack_data), volleys(1))
    (inst,) = out.instances
    assert len(inst.rationale) <= 300 and inst.rationale.endswith("…")
    (w,) = [w for w in out.warnings if w.code == "text_truncated"]
    assert w.severity == "info" and "rationale" in w.detail
    assert inst.code == "a" and inst.counted  # coding itself is untouched


async def test_rationale_at_the_limit_is_untouched(tmp_path, pack_data):
    client = FakeClient(lambda req, n: good(req, lambda vid: [utt("First thing here.", "a", "r" * 300)]))
    out = await run(client, make_pack(tmp_path, pack_data), volleys(1))
    assert out.instances[0].rationale == "r" * 300
    assert not [w for w in out.warnings if w.code == "text_truncated"]
