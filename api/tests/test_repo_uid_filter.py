"""No collection query in the repo layer lacks a uid filter (source-level check)."""

import ast
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parents[1] / "src/onolys_api/repo"
QUERY_CALLS = {"where", "order_by", "stream", "limit", "list_documents", "collection_group"}
# Helpers whose body establishes the uid scope; any other function that queries must call one.
SCOPE_HELPERS = {"_uid_query", "_owned_session", "_session_ref", "_owned_status"}
# Internal worker-only maintenance queries explicitly scan across users (base.py).
SWEEP_QUERIES = {"list_sessions_stuck", "list_uids_with_active_runs"}
# Auth bootstrap: looks a key up by its id before the uid is known (documented in base.py).
UNSCOPED_ALLOWED = {"get_api_key", "_uid_query", "_owned_session"}


def _functions(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            yield node


def _function_contexts(tree, parents=()):
    """Nested transaction functions inherit the scope of the query they close over."""
    for node in ast.iter_child_nodes(tree):
        context = (*parents, node) if isinstance(node, ast.FunctionDef) else parents
        if isinstance(node, ast.FunctionDef):
            yield node, context
        yield from _function_contexts(node, context)


def _called_names(fn):
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            yield f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


def _unscoped_query_functions(tree):
    offenders = []
    for fn, context in _function_contexts(tree):
        names = set(_called_names(fn))
        scope_names = set().union(*(set(_called_names(parent)) for parent in context))
        internal_sweep = any(parent.name in SWEEP_QUERIES for parent in context)
        if (names & QUERY_CALLS) and fn.name not in UNSCOPED_ALLOWED and not internal_sweep:
            if not (scope_names & SCOPE_HELPERS):
                offenders.append(fn.name)
    return offenders


@pytest.mark.parametrize("fname", ["firestore.py"])
def test_every_query_function_is_uid_scoped(fname):
    tree = ast.parse((REPO_DIR / fname).read_text())
    offenders = _unscoped_query_functions(tree)
    assert offenders == [], f"queries without a uid scope: {offenders}"


def test_unscoped_user_queries_still_fail_the_guard():
    tree = ast.parse(
        "def user_lookup(self):\n"
        "    def txn_fn(txn):\n"
        "        return self._client.collection('sessions').stream()\n"
        "    return txn_fn(None)\n"
    )
    assert _unscoped_query_functions(tree) == ["user_lookup", "txn_fn"]


def test_uid_query_helper_filters_on_uid_field():
    src = (REPO_DIR / "firestore.py").read_text()
    tree = ast.parse(src)
    helper = next(f for f in _functions(tree) if f.name == "_uid_query")
    assert '"uid"' in ast.get_source_segment(src, helper)


def _top_level_collection_calls(fn):
    """`self._client.collection(...)`: a top-level collection (subcollections hang off a session ref)."""
    for n in ast.walk(fn):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("collection", "collection_group")
            and isinstance(n.func.value, ast.Attribute)
            and n.func.value.attr == "_client"
        ):
            yield n


def test_top_level_collections_only_via_uid_query_or_by_id_helpers():
    tree = ast.parse((REPO_DIR / "firestore.py").read_text())
    by_id_helpers = {"_top", "get_api_key"}  # document addressed by id; ownership checked after
    bad = [
        fn.name
        for fn in _functions(tree)
        if list(_top_level_collection_calls(fn))
        and "_uid_query" not in set(_called_names(fn))
        and fn.name not in by_id_helpers | SWEEP_QUERIES
    ]
    assert bad == [], f"top-level collection used without _uid_query: {bad}"
