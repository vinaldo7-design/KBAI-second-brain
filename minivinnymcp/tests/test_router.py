"""Improvement slice 5: query router.

Research: plain dense RAG matches/beats GraphRAG on single-hop FACT lookups —
the graph walk pulls in connected-but-redundant notes there. So classify the
query and skip the graph walk for simple fact lookups; keep the full pipeline for
reasoning queries. Reasoning is the SAFE DEFAULT (the system's strength) — only
short, signal-free, single-entity queries take the dense-only fast path.
"""

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.retrieve.router import classify_query


def test_explicit_lookup_is_fact():
    assert classify_query("what is SHAP") == "fact"
    assert classify_query("define DAG") == "fact"
    assert classify_query("who is Judea Pearl") == "fact"


def test_bare_concept_query_is_reasoning():
    # Short concept queries are NOT fact lookups — they want graph expansion.
    assert classify_query("Pearl's ladder") == "reasoning"
    assert classify_query("governance capital") == "reasoning"
    assert classify_query("mastery trap") == "reasoning"


def test_reasoning_signals_route_to_reasoning():
    assert classify_query("difference between interpretability and explainability") == "reasoning"
    assert classify_query("how does PPR work") == "reasoning"
    assert classify_query("compare SHAP vs LIME") == "reasoning"
    assert classify_query("what is the difference between SHAP and LIME") == "reasoning"  # lead + signal → reasoning wins


def test_long_query_is_reasoning():
    assert classify_query("the mastery trap and expertise as optionality in skill") == "reasoning"


def test_empty_query_is_reasoning():
    assert classify_query("") == "reasoning"
    assert classify_query("   ") == "reasoning"
