"""Eval harness: metric correctness + golden-set well-formedness.

Fast (no model, no DB): the live measurement is run via
`python -m kbai.eval.run_golden_eval` before/after retrieval changes. Here we
only prove the metric maths and that the golden set is structurally sound.
"""

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.eval.metrics import hit_at_k, recall_at_k, reciprocal_rank
from kbai.eval.run_golden_eval import evaluate, load_golden


def test_reciprocal_rank():
    assert reciprocal_rank(["a", "b", "c"], ["b"]) == 0.5      # first expected at rank 2
    assert reciprocal_rank(["a", "b", "c"], ["a", "c"]) == 1.0  # first expected at rank 1
    assert reciprocal_rank(["a", "b"], ["z"]) == 0.0           # none present


def test_recall_at_k():
    assert recall_at_k(["a", "b", "c", "d"], ["a", "c", "z"], k=4) == 2 / 3
    assert recall_at_k(["a", "b"], ["a", "b"], k=1) == 0.5      # only top-1 counted
    assert recall_at_k(["a"], [], k=5) == 0.0


def test_hit_at_k():
    assert hit_at_k(["a", "b", "c", "d"], "c", k=3) == 1.0
    assert hit_at_k(["a", "b", "c", "d"], "d", k=3) == 0.0


def test_evaluate_aggregates_correctly():
    golden = [
        {"id": "q1", "query": "x", "primary": "a", "expected": ["a", "b"]},
        {"id": "q2", "query": "y", "primary": "z", "expected": ["z"]},
    ]
    fake = {"x": ["a", "b", "c"], "y": ["m", "z"]}
    rows, summary = evaluate(golden, lambda q: fake[q], k_recall=3, k_primary=1)
    assert summary["mrr"] == round((1.0 + 0.5) / 2, 4)   # q1 a@1=1.0, q2 z@2=0.5
    assert summary["primary_hit@1"] == 0.5               # q1 a@1 hit, q2 z@1 miss
    assert summary["n"] == 2


def test_golden_set_is_well_formed():
    golden = load_golden()
    assert len(golden) >= 10, "golden set should have at least 10 queries"
    ids = [q["id"] for q in golden]
    assert len(set(ids)) == len(ids), "duplicate query ids"
    for q in golden:
        assert q.get("query") and q.get("primary") and q.get("expected")
        assert q["primary"] in q["expected"], f"{q['id']}: primary must be in expected"
        assert len(set(q["expected"])) == len(q["expected"]), f"{q['id']}: duplicate expected"
