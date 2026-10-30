"""Shared test setup.

Tests marked `live` need your real vault: notes, built graph and index, and the
ML models. A clean checkout has none of those, so they skip visibly there instead
of passing without checking anything. Everything else must run anywhere; use the
`toy_vault` fixture for tests that need a vault.
"""

import hashlib
import importlib.util
import os
import re
import shutil
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent
os.environ.setdefault("VAULT_ROOT", str(ROOT))


def _missing_live_requirement() -> str | None:
    for rel in ("06-Maps/vault-graph.json", "06-Maps/vault-embeddings.db", "01-Ideas"):
        if not (ROOT / rel).exists():
            return f"needs the real vault: {rel} is missing"
    if importlib.util.find_spec("sentence_transformers") is None:
        return "needs the ML extra: sentence_transformers is not installed"
    return None


def pytest_collection_modifyitems(items):
    reason = _missing_live_requirement()
    if reason:
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture(autouse=True)
def _no_ml_outside_live_tests(request, monkeypatch):
    """Tests that write notes embed them. Only `live` tests load the real model."""
    if request.node.get_closest_marker("live") is None:
        from kbai.embed import indexer
        monkeypatch.setattr(indexer, "_model", FakeModel())


class FakeModel:
    """Deterministic stand-in for the embedding model: a normalised bag of hashed
    words, so notes sharing words are close and tests need no ML stack."""

    DIM = 384

    def _vec(self, text: str) -> np.ndarray:
        vec = np.zeros(self.DIM, dtype=np.float32)
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vec[int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % self.DIM] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec

    def encode(self, text, normalize_embeddings=True, **_):
        return self._vec(text) if isinstance(text, str) else np.stack([self._vec(t) for t in text])


TOY_NOTES = {
    "metric-targets-decay": (
        "Metric targets decay once people optimise them.",
        "### Builds on\n- [[incentives-shape-behaviour]]: decay needs a motive\n\n"
        "### Contradicts\n- [[managed-metrics-hold]]\n\n"
        "### Analogous to\n- [[overfitting-to-training-data]]\n",
    ),
    "incentives-shape-behaviour": (
        "Incentives shape behaviour in every organisation.",
        "### Builds toward\n- [[metric-targets-decay]]\n",
    ),
    "managed-metrics-hold": (
        "Managed metrics hold their meaning under active stewardship.",
        "### Contradicts\n- [[metric-targets-decay]]\n",
    ),
    "overfitting-to-training-data": (
        "Overfitting to training data fails on new samples.",
        "### Analogous to\n- [[metric-targets-decay]]\n",
    ),
    "rotate-metrics-quarterly": (
        "Rotate metrics quarterly so targets cannot be gamed.",
        "### Operationalises\n- [[metric-targets-decay]]\n",
    ),
}


def toy_note(note_id: str, summary: str, links: str = "") -> str:
    return (
        f"---\nid: '{int(hashlib.sha256(note_id.encode()).hexdigest()[:10], 16)}'\n"
        f"title: {note_id}\ncreated: 2026-10-30\nupdated: 2026-10-30\ntype: idea\n"
        f"status: seedling\nsummary: {summary}\ntags:\n  - topic/test\n  - lens/strategic\n---\n\n"
        f"# {note_id}\n\n## Core Claim\n> {summary}\n\n## Links\n\n{links}"
    )


@pytest.fixture
def toy_vault(tmp_path, monkeypatch):
    """A small real vault in a temp folder, with mini-vinny pointed at it: built
    graph, sqlite index and a fake model. The real vault is never touched."""
    import minivinnymcp.server as mv
    import vault_graph
    from kbai.embed import indexer

    vault = tmp_path / "vault"
    (vault / "01-Ideas").mkdir(parents=True)
    (vault / "06-Maps").mkdir()
    shutil.copy(ROOT / "vault_taxonomy.yaml", vault)
    model = FakeModel()
    for note_id, (summary, links) in TOY_NOTES.items():
        (vault / "01-Ideas" / f"{note_id}.md").write_text(toy_note(note_id, summary, links), encoding="utf-8")
        indexer.embed_note(note_id, summary, vault / "06-Maps" / "vault-embeddings.db",
                           title=note_id, filepath=f"01-Ideas/{note_id}.md", model=model)
    vault_graph.write_graph(vault_graph.build_graph(vault), vault / "06-Maps" / "vault-graph.json")

    monkeypatch.setenv("VAULT_ROOT", str(vault))
    monkeypatch.setattr(indexer, "_model", model)
    monkeypatch.setattr(mv, "_vault_root", vault)
    monkeypatch.setattr(mv, "_DB_PATH", vault / "06-Maps" / "vault-embeddings.db")
    monkeypatch.setattr(mv, "_GRAPH_PATH", vault / "06-Maps" / "vault-graph.json")
    monkeypatch.setattr(mv, "_TAXONOMY_PATH", vault / "vault_taxonomy.yaml")
    monkeypatch.setattr(mv, "_graph", None)
    monkeypatch.setattr(mv, "_get_model", lambda: model)
    monkeypatch.setattr(mv, "_get_reranker", lambda: None)
    return vault
