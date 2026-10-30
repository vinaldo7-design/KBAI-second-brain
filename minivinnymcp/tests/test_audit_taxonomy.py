"""audit_taxonomy must embed in one batch: per-edge encoding took 112s on the
live graph, past the 60s tool-call cap. Uses a toy graph and a fake model."""

import hashlib
from pathlib import Path

import networkx as nx
import numpy as np

_vault_root = Path(__file__).parent.parent.parent

import minivinnymcp.server as mv  # noqa: E402


class FakeModel:
    def __init__(self):
        self.calls = []

    @staticmethod
    def _vec(text):
        seed = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
        v = np.random.default_rng(seed).normal(size=8)
        return v / np.linalg.norm(v)

    def encode(self, text, normalize_embeddings=True):
        self.calls.append(text)
        return self._vec(text) if isinstance(text, str) else np.stack([self._vec(t) for t in text])


class FakeGraph:
    def __init__(self):
        self.g = nx.MultiDiGraph()
        self.g.add_edge("a", "b", type="analogous-to", annotation="why")
        self.g.add_edge("b", "c", type="analogous-to")
        self.g.add_edge("c", "a", type="exemplifies")

    def view(self, **_):
        return self.g

    def node(self, note_id):
        return {"summary": f"summary of {note_id}"}


def _audit(monkeypatch, check_type):
    model = FakeModel()
    monkeypatch.setattr(mv, "_get_model", lambda: model)
    monkeypatch.setattr(mv, "_get_graph", FakeGraph)
    return mv.audit_taxonomy(check_type, "exemplifies"), model


def test_edges_are_embedded_in_a_single_batch(monkeypatch):
    results, model = _audit(monkeypatch, "analogous-to")
    assert len(results) == 2
    assert len(model.calls) == 2  # the against-type description, then one batch


def test_scores_match_one_at_a_time_encoding_and_stay_sorted(monkeypatch):
    results, model = _audit(monkeypatch, "analogous-to")
    desc = model.calls[0]
    expected = {
        ("a", "b"): "summary of a | why | summary of b",
        ("b", "c"): "summary of b | summary of c",
    }
    for row in results:
        text = expected[(row["source"], row["target"])]
        assert row["score"] == round(float(np.dot(model._vec(text), model._vec(desc))), 4)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_type_with_no_edges_returns_empty(monkeypatch):
    results, _ = _audit(monkeypatch, "contradicts")
    assert results == []
