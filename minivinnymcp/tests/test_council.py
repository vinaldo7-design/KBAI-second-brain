"""Stage 5.6: Council Mode tests.

Layered:
  L1 — pure overlap math (build_council_evidence) on hand-crafted lists.
  L2 — run_council with a mock retrieve_fn (no graph, no embeddings).
  L3 — ppr_expand weight_overrides on a synthetic 4-node graph (proves
       profiles produce numerically different rankings).
  L4 — MCP tools registered + (optionally) live council_retrieve smoke
       against the real graph. Skipped if graph/db absent.
"""

import os
import sqlite3
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.contracts import ContextNote, CouncilEvidence
from kbai.council import (
    DEFAULT_COUNCIL_PROFILES,
    build_council_evidence,
    profile_focus_summary,
    run_council,
)
from kbai.cognitive_routing import load_profile

GRAPH_PATH = _vault_root / "06-Maps" / "vault-graph.json"
EMBED_DB = _vault_root / "06-Maps" / "vault-embeddings.db"


# --- L1: overlap math ----------------------------------------------------


def _ctx_note(nid: str) -> ContextNote:
    return ContextNote(note_id=nid, source="ppr", composite_score=0.5)


def test_build_evidence_consensus_and_unique_basic():
    per_profile = {
        "explorer": [_ctx_note(x) for x in ["a", "b", "c"]],
        "operator": [_ctx_note(x) for x in ["b", "c", "d"]],
        "skeptic":  [_ctx_note(x) for x in ["c", "e", "f"]],
    }
    ev = build_council_evidence("q", per_profile, top_k=3)
    assert ev.unanimous == ["c"]                           # all three
    assert "b" in ev.consensus and "c" in ev.consensus     # ≥ 2
    assert ev.unique_to["explorer"] == ["a"]
    assert ev.unique_to["operator"] == ["d"]
    assert sorted(ev.unique_to["skeptic"]) == ["e", "f"]
    assert ev.coverage_count == 6


def test_build_evidence_no_overlap_yields_empty_consensus():
    per_profile = {
        "explorer": [_ctx_note("a")],
        "operator": [_ctx_note("b")],
        "skeptic":  [_ctx_note("c")],
    }
    ev = build_council_evidence("q", per_profile, top_k=1)
    assert ev.consensus == []
    assert ev.unanimous == []
    assert ev.coverage_count == 3


def test_build_evidence_handles_empty_profile():
    per_profile = {
        "explorer": [_ctx_note("a")],
        "operator": [],
        "skeptic":  [_ctx_note("a")],
    }
    ev = build_council_evidence("q", per_profile, top_k=5)
    assert ev.consensus == ["a"]
    assert ev.unique_to["operator"] == []


def test_focus_summary_describes_profile():
    skeptic = load_profile("skeptic")
    s = profile_focus_summary(skeptic)
    assert "contradiction" in s.lower() or "contradicts" in s.lower()


# --- L2: run_council with mock retrieve_fn -------------------------------


def test_run_council_uses_default_profiles():
    canned = {
        "explorer": [_ctx_note("ex1"), _ctx_note("shared")],
        "operator": [_ctx_note("op1"), _ctx_note("shared")],
        "skeptic":  [_ctx_note("sk1"), _ctx_note("shared")],
    }

    def mock_retrieve(query, profile_id, top_k):
        return canned.get(profile_id, [])

    ev = run_council(query="q", profile_ids=None, top_k=2, retrieve_fn=mock_retrieve)
    assert ev.profiles == DEFAULT_COUNCIL_PROFILES
    assert ev.unanimous == ["shared"]
    assert ev.unique_to["explorer"] == ["ex1"]
    # Each per-profile result has a focus summary populated by run_council
    for p in ev.per_profile:
        assert p.focus_summary
        assert p.display_name


def test_run_council_skips_unknown_profile():
    def mock_retrieve(q, p, k):
        return [_ctx_note(f"{p}1")]

    ev = run_council(
        query="q",
        profile_ids=["explorer", "ghost-profile", "operator"],
        top_k=1,
        retrieve_fn=mock_retrieve,
    )
    assert "ghost-profile" not in ev.profiles
    assert "explorer" in ev.profiles
    assert "operator" in ev.profiles


# --- L3: ppr_expand weight_overrides --------------------------------------


def _toy_graph():
    """Build a small synthetic graph that exercises weight overrides.

    A is the seed.
      A --builds-on--> B
      A --analogous-to--> C
      A --operationalises--> D
      A --contradicts--> E

    With base weights (builds-on 1.5, analogous-to 1.3, operationalises 0.85,
    contradicts 1.2), default mode excludes contradicts → E vanishes.
    Skeptic admits contradicts AND boosts it 1.6× → E should rise.
    Explorer boosts analogous-to 1.6× → C should rise.
    """
    from vault_graph_loader import VaultGraph
    data = {
        "vault_root": str(_vault_root),
        "nodes": [{"id": x} for x in "ABCDE"],
        "edges": [
            {"source": "A", "target": "B", "type": "builds-on", "target_exists": True},
            {"source": "A", "target": "C", "type": "analogous-to", "target_exists": True},
            {"source": "A", "target": "D", "type": "operationalises", "target_exists": True},
            {"source": "A", "target": "E", "type": "contradicts", "target_exists": True},
        ],
    }
    # Synthesise plausible taxonomy weights since the test runs without yaml at
    # the synthetic vault root.
    g = VaultGraph(data)
    g.taxonomy_weights = {
        "builds-on": 1.5,
        "analogous-to": 1.3,
        "operationalises": 0.85,
        "contradicts": 1.2,
        "exemplifies": 0.85,
        "challenges": 0.80,
        "mentioned": 0.3,
        "untyped": 0.6,
        "referenced-in": 0.8,
    }
    return g


def test_default_excludes_contradicts_so_E_unreachable():
    g = _toy_graph()
    scores = g.ppr_expand({"A": 1.0}, exclude_types={"contradicts", "mentioned"})
    # E has no inbound edge after contradicts is gated → should rank below seeded A
    assert scores["A"] > scores["E"]


def test_skeptic_admits_contradicts_and_boosts_E():
    g = _toy_graph()
    base = g.ppr_expand({"A": 1.0})  # admits all edges, no overrides
    boosted = g.ppr_expand({"A": 1.0}, weight_overrides={"contradicts": 3.0})
    # Boosting contradicts should increase E's relative score (it's the only
    # contradicts target). Compare relative ranks vs B.
    assert boosted["E"] / boosted["B"] > base["E"] / base["B"]


def test_explorer_boost_raises_C_relative_to_others():
    g = _toy_graph()
    base = g.ppr_expand({"A": 1.0}, exclude_types={"contradicts", "mentioned"})
    explorer_overrides = load_profile("explorer").edge_weight_overrides
    boosted = g.ppr_expand(
        {"A": 1.0},
        exclude_types={"contradicts", "mentioned"},
        weight_overrides=explorer_overrides,
    )
    # Explorer multiplies analogous-to by 1.6 → C's share grows vs B
    assert boosted["C"] / boosted["B"] > base["C"] / base["B"]


# --- L4: MCP tool registration + live smoke -----------------------------


def test_council_tools_registered():
    from minivinnymcp.server import app
    tm = getattr(app, "_tool_manager", None)
    if tm is None:
        return
    names = set(tm._tools.keys())
    assert {"council_retrieve", "cognition_retrieve_as"} <= names


def test_council_retrieve_live_smoke():
    """Exercise the real pipeline against the vault if it's available."""
    if not GRAPH_PATH.exists() or not EMBED_DB.exists():
        return
    from minivinnymcp.server import council_retrieve
    out = council_retrieve(query="mastery and deliberate practice", top_k=5)
    ev = CouncilEvidence(**out)
    assert ev.query == "mastery and deliberate practice"
    assert set(ev.profiles) <= {"explorer", "operator", "skeptic"}
    # Each profile that ran returned at most top_k notes
    for p in ev.per_profile:
        assert len(p.notes) <= 5


def test_council_retrieve_writes_council_event(tmp_path, monkeypatch):
    """Exercise feedback capture without needing the real DB to exist.
    Patch _DB_PATH so the council writes into a clean tmp DB and verify
    the council_events row appears."""
    if not GRAPH_PATH.exists() or not EMBED_DB.exists():
        return
    import minivinnymcp.server as mv
    new_db = tmp_path / "test_events.db"
    # Seed the tmp db by copying the live embedding tables (only `notes`
    # table needed for vault_search; embeddings table is required too)
    import shutil
    shutil.copy(EMBED_DB, new_db)
    monkeypatch.setattr(mv, "_DB_PATH", new_db)
    mv.council_retrieve(query="governance capital", top_k=3)
    db = sqlite3.connect(new_db)
    rows = db.execute("SELECT query_text, profiles FROM council_events").fetchall()
    db.close()
    assert any(r[0] == "governance capital" for r in rows)
