"""Improvement slice 3: BM25 (sparse/keyword) seed + hybrid fusion.

Anthropic's contextual-retrieval result: hybrid keyword+vector beats dense-only.
BM25 over note summaries surfaces literal-keyword matches a dense embedding can
miss, and reciprocal-rank fusion (RRF) merges the two seed lists. Pure/sqlite
unit tests here; the end-to-end hybrid is eyeballed on real queries.
"""

import os
import sqlite3
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.retrieve.sparse import _rrf, bm25_seed


def _fts_db(tmp_path: Path, notes: list[tuple[str, str]]) -> Path:
    db_path = tmp_path / "embeddings.db"
    db = sqlite3.connect(db_path)
    db.execute(
        "CREATE TABLE notes (id TEXT PRIMARY KEY, title TEXT, summary TEXT, "
        "summary_hash TEXT, filepath TEXT)"
    )
    db.execute("CREATE VIRTUAL TABLE notes_fts USING fts5(note_id UNINDEXED, summary)")
    for nid, summ in notes:
        db.execute("INSERT INTO notes (id, title, summary, filepath) VALUES (?,?,?,?)",
                   (nid, nid.title(), summ, f"01-Ideas/{nid}.md"))
        db.execute("INSERT INTO notes_fts(note_id, summary) VALUES (?,?)", (nid, summ))
    db.commit()
    db.close()
    return db_path


def test_bm25_surfaces_literal_keyword_match(tmp_path):
    db = _fts_db(tmp_path, [
        ("xenobots", "Xenobots are living programmable organisms built from frog stem cells."),
        ("ml-basics", "Models learn a function from data to predict an outcome."),
        ("ensembles", "Combining weak models outperforms any single model."),
    ])
    scores, meta = bm25_seed("xenobot programmable", db, seed_k=3)
    assert "xenobots" in scores
    assert list(scores)[0] == "xenobots"            # strongest keyword match first
    assert meta["xenobots"]["summary"].startswith("Xenobots")
    assert meta["xenobots"]["filepath"] == "01-Ideas/xenobots.md"


def test_bm25_graceful_when_no_fts_table(tmp_path):
    # Old DB without notes_fts → empty, never raises (hybrid falls back to dense).
    db_path = tmp_path / "embeddings.db"
    d = sqlite3.connect(db_path)
    d.execute("CREATE TABLE notes (id TEXT)")
    d.commit()
    d.close()
    assert bm25_seed("anything", db_path, seed_k=3) == ({}, {})


def test_bm25_empty_query_returns_empty(tmp_path):
    db = _fts_db(tmp_path, [("a", "some summary text")])
    assert bm25_seed("   ", db, seed_k=3) == ({}, {})


def test_bm25_query_with_punctuation_does_not_crash(tmp_path):
    # FTS5 MATCH is fussy about punctuation; bm25_seed must sanitise to terms.
    db = _fts_db(tmp_path, [("causal", "Causal inference separates correlation from causation.")])
    scores, _ = bm25_seed("correlation != causation?? (causal)", db, seed_k=3)
    assert "causal" in scores


def test_rrf_rewards_agreement_across_rankers():
    fused = _rrf([["a", "b", "c"], ["a", "c", "z"]])
    order = sorted(fused, key=lambda n: -fused[n])
    assert order[0] == "a"                # top of both lists → highest fused score
    assert fused["c"] > fused["z"]        # c appears in both rankers, z in one
    assert fused["c"] > fused["b"]        # c is in both; b only in one
