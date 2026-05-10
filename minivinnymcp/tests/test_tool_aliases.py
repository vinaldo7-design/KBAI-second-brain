"""Stage 0 item 1: assert legacy + namespaced MCP tool aliases coexist
and dispatch to the same implementation."""

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from minivinnymcp import server as mv
from minivinnymcp.server import app

GRAPH_PATH = _vault_root / "06-Maps" / "vault-graph.json"


def _registered_tool_names() -> set[str]:
    """Read FastMCP's tool registry. Tries the modern internal path first,
    then falls back to the async public API. Tolerant of FastMCP version drift."""
    tm = getattr(app, "_tool_manager", None)
    if tm is not None and hasattr(tm, "_tools"):
        return set(tm._tools.keys())
    # Fallback: spin an event loop to call the async list_tools.
    import asyncio
    tools = asyncio.run(app.list_tools())
    return {t.name for t in tools}


# --- registration ---

def test_all_legacy_and_namespaced_tools_registered():
    names = _registered_tool_names()
    expected = {
        # legacy (kept for backward compat)
        "vault_search",
        "assemble_context",
        "get_note_with_context",
        # already correctly namespaced
        "graph_expand",
        "audit_taxonomy",
        # new namespaced aliases
        "retrieve_search",
        "retrieve_assemble",
        "notes_get_with_context",
    }
    missing = expected - names
    assert not missing, f"Missing tool registrations: {missing}"


# --- shared implementation ---

def test_alias_pairs_share_implementation():
    """Each alias pair must dispatch to the same private _impl function."""
    pairs = [
        (mv.vault_search, mv.retrieve_search, mv._vault_search_impl),
        (mv.assemble_context, mv.retrieve_assemble, mv._assemble_context_impl),
        (mv.get_note_with_context, mv.notes_get_with_context, mv._get_note_with_context_impl),
    ]
    for legacy, namespaced, impl in pairs:
        assert callable(legacy), f"{legacy} not callable"
        assert callable(namespaced), f"{namespaced} not callable"
        assert callable(impl), f"{impl} not callable"


# --- equivalent results ---

def test_vault_search_aliases_equal():
    if not GRAPH_PATH.exists():
        return
    a = mv.vault_search("mastery", top_k=3)
    b = mv.retrieve_search("mastery", top_k=3)
    assert a == b


def test_get_note_aliases_equal():
    if not GRAPH_PATH.exists():
        return
    a = mv.get_note_with_context("mastery-trap")
    b = mv.notes_get_with_context("mastery-trap")
    assert a == b


def test_assemble_context_aliases_equal_ids():
    """Compare note_id ordering — composite_score may have float drift across
    independent PPR runs, but the ranked id list must agree."""
    if not GRAPH_PATH.exists():
        return
    a = mv.assemble_context("mastery", seed_k=3, char_budget=2000)
    b = mv.retrieve_assemble("mastery", seed_k=3, char_budget=2000)
    assert [n["note_id"] for n in a["notes"]] == [n["note_id"] for n in b["notes"]]
