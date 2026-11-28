"""Keep LiteLLM's own logging quiet."""

import logging
import os
import sys

LITELLM_LOGGERS = ("litellm", "LiteLLM", "LiteLLM Router", "LiteLLM Proxy")


def quiet_litellm() -> None:
    """Strip LiteLLM's own stderr handlers and pin its loggers to WARNING. Idempotent.

    Call right after a lazy ``import litellm`` (it adds handlers and may reset levels at
    import). Does nothing while litellm is not imported, so api/voice never pay for it.
    """
    os.environ.pop("LITELLM_LOG", None)
    litellm = sys.modules.get("litellm")
    if litellm is None:
        return
    litellm.suppress_debug_info = True
    for name in LITELLM_LOGGERS:
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.propagate = True
        lg.setLevel(logging.WARNING)
