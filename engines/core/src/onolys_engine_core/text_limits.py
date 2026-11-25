"""Length limits for LLM-produced free text (code points), shared by every engine.

Overflow handling is per field and follows the engine's existing pattern for bad model output:
tips are dropped with a violation code and re-proposed once; rationales and reasons are truncated
with an info warning (a whole report must not fail over one long sentence); lists are capped.
"""

TITLE_MAX = 80  # short idea titles (prompt: 3-8 words)
SENTENCE_MAX = 300  # one sentence: rationale, reason, why_it_matters
OBSERVATION_MAX = 400  # "one concise sentence ... 1-2 lines, preserve qualifications"
ALTERNATIVE_MAX = 400  # one or two sentences of replacement wording
QUOTE_MAX = 500  # a quote the model echoes back; stored text always comes from the transcript
MAX_TIPS_PROPOSED = 7  # prompt: "at most 7 tips"
MAX_CITED = 10  # evidence / poor-practice quotes per global


def clip(text: str, limit: int) -> tuple[str, bool]:
    """`text` cut to at most `limit` code points on a word boundary, ending in an ellipsis."""
    if len(text) <= limit:
        return text, False
    cut = text[: limit - 1].rstrip()
    space = cut.rfind(" ")
    if space >= limit * 0.6:
        cut = cut[:space].rstrip(" ,;:")
    return cut + "…", True
