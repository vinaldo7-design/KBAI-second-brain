"""Improvement slice 4: cross-encoder reranking.

A first-stage retriever (dense+BM25 → PPR) optimises recall; a cross-encoder then
re-scores the candidate set by query<->summary relevance to fix ORDER — e.g.
demoting generic map/MOC notes that PPR over-ranks. The reorder logic is unit-
tested here with an injected fake scorer (deterministic, no model); the real
quality is measured by the golden-set eval before/after.
"""

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.retrieve.rerank import rerank_ranked


def test_rerank_promotes_relevant_demotes_hub():
    ranked = [("hub-map", 0.9), ("real-note", 0.5), ("other", 0.1)]
    summaries = {
        "hub-map": "navigation index into the canon concepts",
        "real-note": "specific content directly about widgets",
        "other": "unrelated text",
    }
    # Fake scorer: relevance to 'widgets' — real-note wins despite lowest PPR.
    def scorer(query, texts):
        return [5.0 if "widgets" in t else -5.0 for t in texts]

    out = rerank_ranked("widgets", ranked, lambda nid: summaries[nid], scorer)
    assert [nid for nid, _ in out][0] == "real-note"          # promoted
    assert [nid for nid, _ in out][-1] != "real-note"
    assert {nid for nid, _ in out} == {"hub-map", "real-note", "other"}  # same set


def test_rerank_preserves_score_tuples():
    ranked = [("a", 0.9), ("b", 0.5)]
    out = rerank_ranked("q", ranked, lambda n: "t", lambda q, texts: [1.0, 2.0])
    assert out[0] == ("b", 0.5)   # b scored higher → first; original score kept on the tuple


def test_rerank_empty_is_noop():
    assert rerank_ranked("q", [], lambda n: "", lambda q, t: []) == []


def test_rerank_handles_missing_summary():
    ranked = [("a", 0.9), ("b", 0.5)]
    # b has no summary (→ "") but scorer still returns a score per text; must not crash.
    out = rerank_ranked("q", ranked, lambda n: None, lambda q, texts: [0.0, 1.0])
    assert {nid for nid, _ in out} == {"a", "b"}
    assert out[0][0] == "b"
