"""Improvement slice 2: path-pruning over the PPR ranking.

PathRAG's lesson — graph-RAG's failure mode is redundancy, not insufficiency:
a long PPR tail of weakly-connected notes bloats context and dilutes focus.
prune_redundant_paths trims that tail conservatively: drop notes scoring below
`min_ratio` x the top score, but ALWAYS keep seed notes and never prune below
`keep_min`. Pure function — these are small, deterministic unit tests.
"""

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.retrieve.prune import prune_redundant_paths


def test_prunes_low_reliability_tail():
    ranked = [("a", 1.0)] + [(f"n{i}", 0.5) for i in range(10)] + [("lo", 0.01), ("lo2", 0.004)]
    kept = prune_redundant_paths(ranked, seed_ids=[], min_ratio=0.05, keep_min=10)
    ids = [n for n, _ in kept]
    assert "lo" not in ids and "lo2" not in ids   # below 0.05 * 1.0 = 0.05 → dropped
    assert "a" in ids and "n0" in ids
    assert len(kept) == 11


def test_always_keeps_seed_even_if_below_threshold():
    ranked = [("a", 1.0)] + [(f"n{i}", 0.5) for i in range(10)] + [("seed-lo", 0.001)]
    kept = prune_redundant_paths(ranked, seed_ids=["seed-lo"], min_ratio=0.05, keep_min=5)
    assert "seed-lo" in [n for n, _ in kept]


def test_no_prune_when_list_at_or_below_keep_min():
    ranked = [("a", 1.0), ("b", 0.001), ("c", 0.0005)]
    kept = prune_redundant_paths(ranked, seed_ids=[], min_ratio=0.05, keep_min=10)
    assert kept == ranked   # 3 <= keep_min → untouched (conservative)


def test_keep_min_floor_when_threshold_too_aggressive():
    ranked = [("a", 1.0)] + [(f"n{i}", 0.001) for i in range(20)]
    kept = prune_redundant_paths(ranked, seed_ids=[], min_ratio=0.05, keep_min=10)
    assert len(kept) == 10   # threshold alone keeps only "a"; floor restores top-10


def test_preserves_descending_order():
    ranked = [("a", 1.0), ("b", 0.8), ("c", 0.6), ("d", 0.4), ("e", 0.2)] + [(f"n{i}", 0.15) for i in range(10)]
    kept = prune_redundant_paths(ranked, seed_ids=[], min_ratio=0.05, keep_min=5)
    scores = [s for _, s in kept]
    assert scores == sorted(scores, reverse=True)


def test_empty_input():
    assert prune_redundant_paths([], seed_ids=[]) == []
