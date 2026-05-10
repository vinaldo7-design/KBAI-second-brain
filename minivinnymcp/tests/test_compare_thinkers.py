"""Stage 5.6.9 — cognition_compare_profiles tests.

Layered:
  L1 — Jaccard divergence math (no graph/embeddings).
  L2 — MCP tool registered + basic dispatch via mock _retrieve_with_profile.
  L3 — Single-profile edge case (divergence=0.0).
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.contracts import ContextNote, ProfileComparison
from minivinnymcp.server import cognition_compare_profiles


# ── helpers ──────────────────────────────────────────────────────────────────

def _note(nid: str, score: float = 0.5) -> dict:
    return {
        "note_id": nid, "title": nid, "summary": None,
        "content": None, "composite_score": score,
        "source": "ppr", "via_edge": None, "parent": None,
        "reasoning_path": None,
    }


def _mock_retrieve(notes_per_profile: dict[str, list[str]]):
    """Return a _retrieve_with_profile side_effect that yields fixed note lists."""
    def _impl(query, profile_id, top_k, **kwargs):
        nids = notes_per_profile.get(profile_id, [])
        return {"notes": [_note(n) for n in nids], "query": query}
    return _impl


# ── L1: Jaccard divergence math ──────────────────────────────────────────────

def test_identical_profiles_divergence_zero():
    notes = {"p1": ["a", "b", "c"], "p2": ["a", "b", "c"]}
    with patch("minivinnymcp.server._retrieve_with_profile", side_effect=_mock_retrieve(notes)):
        result = cognition_compare_profiles("q", ["p1", "p2"], top_k=3)
    assert result["divergence_score"] == 0.0


def test_disjoint_profiles_divergence_one():
    notes = {"p1": ["a", "b", "c"], "p2": ["d", "e", "f"]}
    with patch("minivinnymcp.server._retrieve_with_profile", side_effect=_mock_retrieve(notes)):
        result = cognition_compare_profiles("q", ["p1", "p2"], top_k=3)
    assert result["divergence_score"] == 1.0


def test_partial_overlap_divergence_between():
    # union=4, intersection=2 → (4-2)/4 = 0.5
    notes = {"p1": ["a", "b", "c", "d"], "p2": ["c", "d", "e", "f"]}
    with patch("minivinnymcp.server._retrieve_with_profile", side_effect=_mock_retrieve(notes)):
        result = cognition_compare_profiles("q", ["p1", "p2"], top_k=4)
    assert 0.0 < result["divergence_score"] < 1.0


def test_single_profile_divergence_zero():
    notes = {"default": ["a", "b"]}
    with patch("minivinnymcp.server._retrieve_with_profile", side_effect=_mock_retrieve(notes)):
        result = cognition_compare_profiles("q", ["default"], top_k=2)
    assert result["divergence_score"] == 0.0


def test_three_profiles_partial_overlap():
    notes = {
        "p1": ["a", "b", "c"],
        "p2": ["b", "c", "d"],
        "p3": ["c", "d", "e"],
    }
    with patch("minivinnymcp.server._retrieve_with_profile", side_effect=_mock_retrieve(notes)):
        result = cognition_compare_profiles("q", ["p1", "p2", "p3"], top_k=3)
    # union={a,b,c,d,e}=5, intersection={c}=1 → (5-1)/5 = 0.8
    assert result["divergence_score"] == 0.8


# ── L2: return shape ─────────────────────────────────────────────────────────

def test_return_shape_has_required_keys():
    notes = {"explorer": ["x", "y"], "skeptic": ["y", "z"]}
    with patch("minivinnymcp.server._retrieve_with_profile", side_effect=_mock_retrieve(notes)):
        result = cognition_compare_profiles("mastery", ["explorer", "skeptic"], top_k=2)
    assert "query" in result
    assert "profiles" in result
    assert "per_profile" in result
    assert "divergence_score" in result
    assert result["query"] == "mastery"
    assert set(result["profiles"]) == {"explorer", "skeptic"}


def test_per_profile_note_lists_populated():
    notes = {"operator": ["op-a", "op-b"], "builder": ["bl-a", "bl-b"]}
    with patch("minivinnymcp.server._retrieve_with_profile", side_effect=_mock_retrieve(notes)):
        result = cognition_compare_profiles("q", ["operator", "builder"], top_k=2)
    per = result["per_profile"]
    assert "operator" in per
    assert [n["note_id"] for n in per["operator"]] == ["op-a", "op-b"]


# ── L3: MCP tool registered ───────────────────────────────────────────────────

def test_tool_registered_in_mcp_app():
    from minivinnymcp.server import app
    tool_names = [t.name for t in app._tool_manager.list_tools()]
    assert "cognition_compare_profiles" in tool_names
