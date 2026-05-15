"""Stage 10: /imagine tests.

Layered:
  L1 — prompt rendering on a synthetic signature (no graph).
  L2 — signature extraction on a hand-built VaultGraph (no embeddings).
  L3 — end-to-end imagine() over the synthetic graph.
  L4 — MCP tool registered + smoke test against the real vault graph
       (skipped if graph absent).
"""

import json
import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.imagination import MODES, build_synthesis_prompt, extract_cluster_signature, imagine
from vault_graph_loader import VaultGraph

GRAPH_PATH = _vault_root / "06-Maps" / "vault-graph.json"


# --- Synthetic graph fixture --------------------------------------------------


def _synthetic_graph() -> VaultGraph:
    """Build a 5-node graph as a minimal cluster for unit tests.

      A --builds-on--> B
      A --builds-on--> C
      C --contradicts--> B
      D --builds-on--> A         (so A is high in-degree)
      E --analogous-to--> A
    """
    data = {
        "nodes": [
            {"id": "a", "title": "A", "summary": "concept a about governance"},
            {"id": "b", "title": "B", "summary": "concept b about restraint"},
            {"id": "c", "title": "C", "summary": "concept c about scaling"},
            {"id": "d", "title": "D", "summary": "concept d about lineage"},
            {"id": "e", "title": "E", "summary": "concept e analogous"},
        ],
        "edges": [
            {"source": "a", "target": "b", "type": "builds-on"},
            {"source": "a", "target": "c", "type": "builds-on"},
            {"source": "c", "target": "b", "type": "contradicts"},
            {"source": "d", "target": "a", "type": "builds-on"},
            {"source": "e", "target": "a", "type": "analogous-to"},
        ],
    }
    return VaultGraph(data)


# --- L1: prompt rendering -----------------------------------------------------


def test_modes_are_five():
    assert set(MODES) == {"extend", "fracture", "bridge", "deepen", "historicise"}


def test_build_prompt_all_modes_render():
    signature = {
        "seed": "x",
        "seed_title": "X",
        "seed_summary": "test summary",
        "depth": 1,
        "size": 3,
        "edge_distribution": {"builds-on": 2},
        "contradicts_ratio": 0.0,
        "load_bearing": [{"note_id": "y", "in_degree": 2, "contradicts_in": 0,
                          "unchallenged_load_score": 2.0}],
        "frontier": [{"note_id": "z", "title": "Z"}],
        "thematic_vocabulary": [("governance", 3), ("restraint", 2)],
        "member_ids": ["x", "y", "z"],
    }
    for mode in MODES:
        prompt = build_synthesis_prompt(signature, mode, k=3)
        # Sanity: the mode word, k, and at least one signature field appear.
        assert mode in prompt
        assert "Return a JSON list of 3 proposed domains" in prompt
        assert "governance" in prompt
        assert "y" in prompt  # load-bearing node mentioned


def test_build_prompt_rejects_unknown_mode():
    try:
        build_synthesis_prompt({"seed": "x"}, "speculate")
    except ValueError as e:
        assert "unknown mode" in str(e)
        return
    assert False, "expected ValueError"


# --- L2: signature extraction on synthetic graph ------------------------------


def test_signature_collects_subgraph_at_depth_1():
    g = _synthetic_graph()
    sig = extract_cluster_signature(g, "a", depth=1)
    # A's depth-1 neighbours: B, C (out via builds-on), D, E (in via builds-on, analogous-to)
    assert sig["seed"] == "a"
    assert sig["size"] == 5
    assert set(sig["member_ids"]) == {"a", "b", "c", "d", "e"}


def test_signature_edge_distribution():
    g = _synthetic_graph()
    sig = extract_cluster_signature(g, "a", depth=1)
    dist = sig["edge_distribution"]
    # 3 builds-on (a→b, a→c, d→a), 1 contradicts (c→b), 1 analogous-to (e→a)
    assert dist.get("builds-on") == 3
    assert dist.get("contradicts") == 1
    assert dist.get("analogous-to") == 1


def test_signature_load_bearing_identifies_a_and_b():
    """A has 1 builds-on incoming (d→a); B has 1 builds-on (a→b) + 1 contradicts (c→b).
    The high-in-degree-low-contradicts-ratio scorer should rank A above B."""
    g = _synthetic_graph()
    sig = extract_cluster_signature(g, "a", depth=1)
    lb_ids = [item["note_id"] for item in sig["load_bearing"]]
    # B has in_degree=2 (typed: builds-on from a + contradicts from c) so it shows up.
    # A only has in_degree 1 (builds-on from d) + 1 analogous-to from e = 2.
    # Both qualify (in_degree >= 2). A has 0 contradicts_in, B has 1 — A scores higher.
    assert "a" in lb_ids
    if "b" in lb_ids:
        idx_a = lb_ids.index("a")
        idx_b = lb_ids.index("b")
        assert idx_a < idx_b  # a (unchallenged) ranks above b (challenged)


def test_signature_frontier_excludes_nodes_with_outgoing_builds():
    g = _synthetic_graph()
    sig = extract_cluster_signature(g, "a", depth=1)
    frontier_ids = {item["note_id"] for item in sig["frontier"]}
    # Outgoing builds-on inside cluster: a→b, a→c, d→a → frontier excludes a, d.
    # c only has outgoing contradicts (c→b), no builds-on → c IS frontier.
    # b and e have no outgoing builds-on either → both frontier.
    assert "b" in frontier_ids
    assert "e" in frontier_ids
    assert "c" in frontier_ids
    assert "a" not in frontier_ids
    assert "d" not in frontier_ids


def test_signature_thematic_vocabulary_excludes_stopwords():
    g = _synthetic_graph()
    sig = extract_cluster_signature(g, "a", depth=1)
    vocab_words = {w for w, _ in sig["thematic_vocabulary"]}
    assert "concept" in vocab_words  # signal
    assert "the" not in vocab_words   # stopword
    assert "about" not in vocab_words  # stopword (actually filtered by length too)


def test_signature_contradicts_ratio_is_correct():
    g = _synthetic_graph()
    sig = extract_cluster_signature(g, "a", depth=1)
    # Typed edges (excluding untyped/mentioned/referenced-in): 3 builds-on + 1 contradicts + 1 analogous = 5
    # contradicts/total = 1/5 = 0.2
    assert sig["contradicts_ratio"] == 0.2


# --- L3: end-to-end imagine() -------------------------------------------------


def test_imagine_returns_bundle():
    g = _synthetic_graph()
    out = imagine(g, seed="a", mode="fracture", depth=1, k=4)
    assert out["seed"] == "a"
    assert out["mode"] == "fracture"
    assert out["k"] == 4
    assert "cluster_signature" in out
    assert "synthesis_prompt" in out
    assert "fracture" in out["synthesis_prompt"]


def test_imagine_unknown_mode_returns_error():
    g = _synthetic_graph()
    out = imagine(g, seed="a", mode="speculate")
    assert "error" in out
    assert "unknown mode" in out["error"]


def test_imagine_unknown_seed_returns_error():
    g = _synthetic_graph()
    out = imagine(g, seed="nonexistent-xyz", mode="extend")
    assert "error" in out


def test_imagine_all_five_modes_produce_distinct_prompts():
    """Each mode should produce a meaningfully different synthesizer prompt."""
    g = _synthetic_graph()
    prompts = {m: imagine(g, seed="a", mode=m, depth=1)["synthesis_prompt"] for m in MODES}
    assert len(set(prompts.values())) == 5  # all distinct


# --- L4: MCP tool + live smoke test ------------------------------------------


def test_mcp_tool_registered():
    """imagine should be importable from server module."""
    from minivinnymcp.server import imagine as tool_imagine
    assert callable(tool_imagine)


def test_live_imagine_against_real_graph():
    """Smoke test against the actual vault. Skipped if graph absent."""
    if not GRAPH_PATH.exists():
        return
    from minivinnymcp.server import imagine as tool_imagine
    out = tool_imagine(seed="governance-capital", mode="fracture", depth=2, k=5)
    assert "error" not in out, f"Unexpected error: {out.get('error')}"
    sig = out["cluster_signature"]
    assert sig["size"] > 5, "governance-capital cluster should be substantial"
    assert "contradicts_ratio" in sig
    assert "load_bearing" in sig
    assert "synthesis_prompt" in out
    assert "fracture" in out["synthesis_prompt"]
