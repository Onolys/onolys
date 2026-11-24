"""Pure selection validation and unit planning for eval runs (server authority).

Inputs and outputs are plain data so the web client can mirror them against the
shared table fixtures in ``eval/fixtures/selection_cases.json``.
"""

MAX_UNITS = 499


class SelectionError(ValueError):
    """A model/tier/effort selection that cannot produce valid combos."""


class RunTooLarge(ValueError):
    def __init__(self, count: int):
        self.count = count
        super().__init__(
            f"Run has {count} units; the maximum is {MAX_UNITS}. "
            "Remove sessions, combos or repeats."
        )


def combo_key(combo: dict) -> str:
    return f"{combo['model']}/{combo['tier']}/{combo['effort']}"


def validate_selection(models: dict, selection: dict, needs_combos: bool = True):
    """Return (combos, dropped) for a selection.

    models: {model_id: {tier_id: [efforts]}}; selection: {models, tiers, efforts}.
    dropped lists combos removed because the tier lacks the effort. Raises
    SelectionError with a specific message; an empty product is an error only
    when needs_combos (some non-human engine is selected).
    """
    sel_models, sel_tiers, sel_efforts = (
        list(selection.get(k) or []) for k in ("models", "tiers", "efforts")
    )
    owner = {t: m for m, tiers in models.items() for t in tiers}
    known_efforts = {e for tiers in models.values() for efforts in tiers.values() for e in efforts}
    for m in sel_models:
        if m not in models:
            raise SelectionError(f"Unknown model '{m}'.")
    for t in sel_tiers:
        if t not in owner:
            raise SelectionError(f"Unknown tier '{t}'.")
    for e in sel_efforts:
        if e not in known_efforts:
            raise SelectionError(f"Unknown effort '{e}'.")
    for m in sel_models:
        if not any(owner[t] == m for t in sel_tiers):
            raise SelectionError(f"Model '{m}' has no selected tier.")
    for t in sel_tiers:
        if owner[t] not in sel_models:
            raise SelectionError(
                f"Tier '{t}' belongs to model '{owner[t]}', which is not selected."
            )
    if sel_tiers:
        for e in sel_efforts:
            if not any(e in models[owner[t]][t] for t in sel_tiers):
                raise SelectionError(f"Effort '{e}' is not supported by any selected tier.")
    combos, dropped = [], []
    for m in sel_models:
        for t in sel_tiers:
            if owner[t] != m:
                continue
            for e in sel_efforts:
                target = combos if e in models[m][t] else dropped
                target.append({"model": m, "tier": t, "effort": e})
    if needs_combos and not combos:
        raise SelectionError("Selection has no valid model, tier and effort combination.")
    return combos, dropped


def plan_units(sessions: list, engines: list, combos: list, repeats: int) -> list:
    """Expand sessions x engines x combos x repeats; human has one unit per session.

    sessions: [{session_id, has_gold?}]. Raises RunTooLarge above 499 units.
    A human unit for a session without gold is kept but flagged skipped: no_gold.
    """
    ai = sum(e != "human" for e in engines)
    count = len(sessions) * (int("human" in engines) + ai * len(combos) * repeats)
    if count > MAX_UNITS:
        raise RunTooLarge(count)
    units = []
    for session in sessions:
        for engine in engines:
            if engine == "human":
                unit = {
                    "session_id": session["session_id"],
                    "engine": engine,
                    "combo": None,
                    "combo_key": None,
                    "repeat": 0,
                }
                if session.get("has_gold", True) is False:
                    unit["skipped"] = "no_gold"
                units.append(unit)
                continue
            for combo in combos:
                for repeat in range(repeats):
                    units.append(
                        {
                            "session_id": session["session_id"],
                            "engine": engine,
                            "combo": dict(combo),
                            "combo_key": combo_key(combo),
                            "repeat": repeat,
                        }
                    )
    return units
