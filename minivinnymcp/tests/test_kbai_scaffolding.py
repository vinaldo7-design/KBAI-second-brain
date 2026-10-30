"""Stage 0 items 6-10: scaffolding modules exist and behave to spec.

These are scaffolding tests — they verify shape and contracts, not deep
behaviour. Real coverage lands as the modules grow in Stages 1+.
"""

from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent

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


