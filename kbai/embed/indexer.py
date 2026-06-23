"""Capture-pipeline Task 3 (Part A): reusable per-note embedding indexer.

Extracted from vault_embed.py so that BOTH the batch builder (vault_embed.main)
and the on-write reindex hook (kbai.embed.reindex_hooks.update_note_embeddings)
share ONE embed path. Closes the same-session staleness window: a note created
via write_create_note is embedded immediately, so semantic search can find it
without waiting for a full re-embed.

Reuses vault_search.{serialize_embedding, QUERY_PREFIX, MODEL_NAME} — these are
NOT duplicated here. Documents (summaries) are embedded WITHOUT the QUERY_PREFIX;
only queries get the prefix (preserved from vault_embed.py). The summary SHA-256
hash drives an idempotent UPSERT: an unchanged summary is skipped.

Dependencies: sqlite-vec, sentence-transformers.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Optional

import sqlite_vec

# Single source of truth for the model name + (de)serialisation lives in
# vault_search. Importing here avoids drift between embed and query paths.
from vault_search import MODEL_NAME, serialize_embedding  # noqa: F401

EMBED_DIM = 384

# Lazy module-level model cache. The first embed_note / get_model call in a
# process loads BGE-small (~33MB) once; subsequent calls reuse it.
_model = None


def get_model():
    """Return a cached SentenceTransformer(MODEL_NAME), loading it on first use.

    Lazy import of sentence_transformers keeps module import cheap for callers
    that only need hash_summary / serialize_embedding.
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def hash_summary(s: str) -> str:
    """16-hex-char SHA-256 prefix of a summary string.

    Must match vault_embed.hash_summary exactly so the two embed paths agree on
    whether a summary is unchanged (otherwise an on-write embed and a later
    batch run would each think the other is stale).
    """
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def init_db(db: sqlite3.Connection) -> None:
    """Create the notes + note_vectors tables if absent (idempotent)."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            title TEXT,
            summary TEXT,
            summary_hash TEXT,
            filepath TEXT
        )
        """
    )
    db.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS note_vectors USING vec0(
            note_id TEXT PRIMARY KEY,
            embedding FLOAT[{EMBED_DIM}]
        )
        """
    )
    # BM25 keyword index over summaries (hybrid retrieval, slice 3). Kept in sync
    # with the vector index by embed_note, so both refresh on the same write.
    db.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(note_id UNINDEXED, summary)"
    )
    db.commit()


def open_db(db_path) -> sqlite3.Connection:
    """Open a sqlite connection with the sqlite-vec extension loaded."""
    db = sqlite3.connect(str(db_path))
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    return db


def embed_note(
    note_id: str,
    summary: str,
    db_path,
    *,
    title: str = "",
    filepath: str = "",
    model=None,
    db: Optional[sqlite3.Connection] = None,
) -> bool:
    """Embed (or refresh) a single note's summary into the sqlite-vec index.

    Opens the DB at ``db_path`` (creating the schema if needed), computes the
    SHA-256 summary hash, and UPSERTS the ``notes`` row + ``note_vectors``
    embedding. If a row already exists with the SAME summary_hash, nothing is
    written and ``False`` is returned (idempotent skip). Returns ``True`` when an
    embedding was (re)written.

    Documents are embedded WITHOUT QUERY_PREFIX — only queries get the prefix.

    Args:
        note_id:  stable id (used as the primary key in both tables).
        summary:  the text that gets embedded; empty/whitespace summaries are
                  skipped (return False) — there is nothing to index.
        db_path:  path to the sqlite-vec embeddings DB.
        title:    optional display title for the notes row.
        filepath: optional vault-relative path for the notes row.
        model:    optional preloaded SentenceTransformer; defaults to get_model().
        db:       optional caller-managed connection (the batch builder reuses one
                  connection across many notes). When omitted, a connection is
                  opened and closed per call.
    """
    if not isinstance(note_id, str) or not note_id:
        raise ValueError("note_id must be a non-empty string")
    if summary is None or not str(summary).strip():
        return False

    summary = str(summary)
    h = hash_summary(summary)

    owns_db = db is None
    if owns_db:
        db = open_db(db_path)
    try:
        init_db(db)

        existing = db.execute(
            "SELECT summary_hash FROM notes WHERE id = ?", (note_id,)
        ).fetchone()
        if existing is not None and existing[0] == h:
            return False  # unchanged — idempotent skip

        if model is None:
            model = get_model()
        vec = model.encode(summary, normalize_embeddings=True)

        db.execute(
            """
            INSERT OR REPLACE INTO notes
            (id, title, summary, summary_hash, filepath)
            VALUES (?, ?, ?, ?, ?)
            """,
            (note_id, title, summary, h, filepath),
        )
        db.execute("DELETE FROM note_vectors WHERE note_id = ?", (note_id,))
        db.execute(
            "INSERT INTO note_vectors (note_id, embedding) VALUES (?, ?)",
            (note_id, serialize_embedding(vec)),
        )
        # Keep the BM25 keyword index in sync (hybrid retrieval, slice 3).
        db.execute("DELETE FROM notes_fts WHERE note_id = ?", (note_id,))
        db.execute(
            "INSERT INTO notes_fts (note_id, summary) VALUES (?, ?)",
            (note_id, summary),
        )
        db.commit()
        return True
    finally:
        if owns_db:
            db.close()
