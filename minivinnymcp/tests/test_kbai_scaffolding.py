"""Stage 0 items 6-10: scaffolding modules exist and behave to spec.

These are scaffolding tests — they verify shape and contracts, not deep
behaviour. Real coverage lands as the modules grow in Stages 1+.
"""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

# --- item 6: sampler ---

def test_sampler_handles_missing_db():
    from kbai.eval.sample_queries_from_note_hits import sample_query_hashes
    out = sample_query_hashes(Path("/nonexistent/db.sqlite"))
    assert out == []


def test_sampler_handles_empty_table(tmp_path):
    from kbai.eval.sample_queries_from_note_hits import sample_query_hashes
    db_path = tmp_path / "test.db"
    db = sqlite3.connect(db_path)
    db.execute(
        "CREATE TABLE note_hits (query_hash TEXT, note_id TEXT, rank INTEGER, mode TEXT, ts INTEGER)"
    )
    db.commit()
    db.close()
    assert sample_query_hashes(db_path) == []


def test_sampler_ranks_by_weighted_count(tmp_path):
    from kbai.eval.sample_queries_from_note_hits import sample_query_hashes
    db_path = tmp_path / "test.db"
    db = sqlite3.connect(db_path)
    db.execute(
        "CREATE TABLE note_hits (query_hash TEXT, note_id TEXT, rank INTEGER, mode TEXT, ts INTEGER)"
    )
    import time
    now = int(time.time())
    rows = (
        # qA seen 3 times today
        [("qA", f"n{i}", i, "standard", now) for i in range(3)]
        # qB seen 5 times today
        + [("qB", f"n{i}", i, "standard", now) for i in range(5)]
    )
    db.executemany("INSERT INTO note_hits VALUES (?,?,?,?,?)", rows)
    db.commit()
    db.close()
    out = sample_query_hashes(db_path, n=5)
    assert out[0]["query_hash"] == "qB"
    assert out[1]["query_hash"] == "qA"


def test_sampler_writes_draft(tmp_path):
    from kbai.eval.sample_queries_from_note_hits import write_draft
    out = write_draft([{"id": "q01", "query_hash": "abc", "weighted_count": 1.0}], tmp_path / "out.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["queries"][0]["id"] == "q01"


# --- item 7: eval runner ---

def test_eval_runner_handles_missing_queries(tmp_path, capsys):
    from kbai.eval.run_retrieval_eval import _load_queries
    queries = _load_queries(tmp_path / "missing.json")
    assert queries == []


def test_eval_runner_loads_queries(tmp_path):
    from kbai.eval.run_retrieval_eval import _load_queries
    p = tmp_path / "q.json"
    p.write_text(json.dumps({"queries": [{"id": "q1", "query_text": "hi"}]}))
    assert _load_queries(p) == [{"id": "q1", "query_text": "hi"}]


# --- item 8: reindex hooks ---

def test_update_note_embeddings_skips_unknown_note():
    # Task 3: the embed hook is now REAL (no longer a stub). An unknown note_id
    # has no file to read, so it returns a soft "skipped" status rather than the
    # old "stub" sentinel — and still never raises.
    from kbai.embed.reindex_hooks import update_note_embeddings
    out = update_note_embeddings("foo")
    assert out["status"] == "skipped"
    assert out["note_id"] == "foo"
    assert out["reason"] == "note_file_not_found"


def test_update_note_edges_skips_unknown_note():
    # The graph reindex hook is now REAL (incremental merge). An unknown note_id
    # has no file to reparse, so it returns a soft "skipped", and never raises.
    from kbai.graph.reindex_hooks import update_note_edges
    out = update_note_edges("foo")
    assert out["status"] == "skipped"
    assert out["note_id"] == "foo"


def test_reindex_hooks_reject_empty():
    from kbai.embed.reindex_hooks import update_note_embeddings
    from kbai.graph.reindex_hooks import update_note_edges
    assert update_note_embeddings("")["status"] == "error"
    assert update_note_edges("")["status"] == "error"


def test_reindex_hooks_do_not_trigger_full_rebuild(monkeypatch):
    """Spy on vault_graph.build_graph and vault_embed.main to ensure neither
    is called during a per-note reindex hook invocation."""
    import vault_graph
    import vault_embed
    called: dict[str, int] = {"build_graph": 0, "embed_main": 0}
    monkeypatch.setattr(vault_graph, "build_graph",
                        lambda *a, **kw: called.__setitem__("build_graph", called["build_graph"] + 1))
    monkeypatch.setattr(vault_embed, "main",
                        lambda *a, **kw: called.__setitem__("embed_main", called["embed_main"] + 1))
    from kbai.embed.reindex_hooks import update_note_embeddings
    from kbai.graph.reindex_hooks import update_note_edges
    update_note_embeddings("some-note")
    update_note_edges("some-note")
    assert called == {"build_graph": 0, "embed_main": 0}


# --- item 9: voice profile ---

def test_voice_hash_stable_for_same_input():
    from kbai.voice_profile import compute_voice_exemplar_hash
    notes = [("a", "body 1"), ("b", "body 2")]
    h1 = compute_voice_exemplar_hash(notes)
    h2 = compute_voice_exemplar_hash(list(reversed(notes)))  # order-independent
    assert h1 == h2
    assert len(h1) == 64


def test_voice_hash_changes_on_content_change():
    from kbai.voice_profile import compute_voice_exemplar_hash
    a = compute_voice_exemplar_hash([("a", "body 1")])
    b = compute_voice_exemplar_hash([("a", "body 1!")])
    assert a != b


def test_voice_hash_changes_on_id_change():
    from kbai.voice_profile import compute_voice_exemplar_hash
    a = compute_voice_exemplar_hash([("a", "body")])
    b = compute_voice_exemplar_hash([("a-renamed", "body")])
    assert a != b


def test_voice_profile_cache_roundtrip(tmp_path):
    from kbai.voice_profile import build_voice_profile, save_cached_profile, load_cached_profile
    p = build_voice_profile("deadbeef", exemplar_ids=["a", "b"], profile_data={"x": 1})
    save_cached_profile(p, cache_dir=tmp_path)
    loaded = load_cached_profile("deadbeef", cache_dir=tmp_path)
    assert loaded is not None
    assert loaded.profile_hash == "deadbeef"
    assert loaded.exemplar_ids == ["a", "b"]
    assert loaded.profile_data == {"x": 1}


def test_voice_profile_cache_miss_returns_none(tmp_path):
    from kbai.voice_profile import load_cached_profile
    assert load_cached_profile("missing", cache_dir=tmp_path) is None


# --- item 10: instrumentation ---

def test_record_note_hits_writes_expected_schema(tmp_path):
    from kbai.instrumentation import record_note_hits
    db_path = tmp_path / "hits.db"
    record_note_hits(
        db_path,
        query="test query",
        results=[{"note_id": "n1"}, {"note_id": "n2"}],
        mode="standard",
    )
    db = sqlite3.connect(db_path)
    rows = db.execute("SELECT query_hash, note_id, rank, mode FROM note_hits ORDER BY rank").fetchall()
    db.close()
    assert len(rows) == 2
    assert rows[0][1] == "n1"
    assert rows[0][3] == "standard"


def test_record_note_hits_populates_query_log(tmp_path):
    from kbai.instrumentation import record_note_hits
    db_path = tmp_path / "hits.db"
    record_note_hits(db_path, query="hello world", results=[{"note_id": "n1"}], mode="standard")
    record_note_hits(db_path, query="hello world", results=[{"note_id": "n2"}], mode="standard")
    db = sqlite3.connect(db_path)
    rows = db.execute("SELECT query_text, seen_count FROM query_log").fetchall()
    db.close()
    assert len(rows) == 1
    assert rows[0][0] == "hello world"
    assert rows[0][1] == 2  # incremented


def test_log_retrieval_event_writes_row(tmp_path):
    from kbai.instrumentation import log_retrieval_event
    db_path = tmp_path / "events.db"
    log_retrieval_event(
        db_path,
        query="q",
        mode="sparring",
        latency_ms=42.5,
        num_candidates=10,
        graph_nodes_touched=37,
        top_note_ids=["a", "b", "c"],
    )
    db = sqlite3.connect(db_path)
    cols = [r[1] for r in db.execute("PRAGMA table_info(retrieval_events)").fetchall()]
    rows = db.execute("SELECT mode, latency_ms, top_note_ids FROM retrieval_events").fetchall()
    db.close()
    assert {"ts", "query_hash", "mode", "latency_ms", "num_candidates",
            "graph_nodes_touched", "top_note_ids"} <= set(cols)
    assert rows[0][0] == "sparring"
    assert rows[0][1] == 42.5
    assert rows[0][2] == "a,b,c"


def test_instrumentation_never_raises_on_bad_db():
    """Best-effort guarantee: failures must not propagate."""
    from kbai.instrumentation import record_note_hits, log_retrieval_event
    record_note_hits("/nonexistent/dir/x.db",
                     query="q", results=[{"note_id": "n"}], mode="standard")
    log_retrieval_event("/nonexistent/dir/x.db",
                        query="q", mode="standard", latency_ms=1.0,
                        num_candidates=0, graph_nodes_touched=0, top_note_ids=[])
