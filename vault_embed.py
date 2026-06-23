#!/usr/bin/env python3
"""
vault_embed.py — Build/refresh local vector index over note summaries.

Reads 06-Maps/vault-graph.json, embeds each note's summary using a small
local model (BGE-small, ~33MB, runs on CPU), stores embeddings in
06-Maps/vault-embeddings.db.

Incremental: only re-embeds notes whose summary has changed since last run.
Idempotent. Run after vault_graph.py to keep the index current.

Dependencies: pip install sqlite-vec sentence-transformers
"""

import argparse
import hashlib
import json
import sqlite3
import struct
from pathlib import Path

import sqlite_vec
from sentence_transformers import SentenceTransformer

VAULT_ROOT = Path(__file__).parent
GRAPH_JSON = VAULT_ROOT / "06-Maps" / "vault-graph.json"
DB_PATH = VAULT_ROOT / "06-Maps" / "vault-embeddings.db"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384


def hash_summary(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def serialize_embedding(vec) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def node_filepath(node: dict) -> str:
    """Return a graph node's vault-relative path.

    vault_graph.py serialises Node dataclasses (via asdict), which store the
    path under the key ``path``. Older/alternate dumps may use ``filepath``;
    fall back to that for safety. Returns "" if neither is present.
    """
    return node.get("path") or node.get("filepath", "") or ""


def init_db(db: sqlite3.Connection):
    db.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            title TEXT,
            summary TEXT,
            summary_hash TEXT,
            filepath TEXT
        )
    """)
    db.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS note_vectors USING vec0(
            note_id TEXT PRIMARY KEY,
            embedding FLOAT[{EMBED_DIM}]
        )
    """)
    db.commit()


def open_db():
    db = sqlite3.connect(DB_PATH)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    return db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true",
                        help="Re-embed every note regardless of hash")
    args = parser.parse_args()

    if not GRAPH_JSON.exists():
        raise SystemExit(f"Missing {GRAPH_JSON}. Run vault_graph.py first.")

    data = json.loads(GRAPH_JSON.read_text())
    nodes_with_summary = [n for n in data["nodes"] if n.get("summary")]
    skipped_no_summary = len(data["nodes"]) - len(nodes_with_summary)

    print(f"Loading model {MODEL_NAME} (first run downloads ~33MB)...")
    model = SentenceTransformer(MODEL_NAME)

    db = open_db()
    init_db(db)

    existing = {row[0]: row[1] for row in db.execute(
        "SELECT id, summary_hash FROM notes")}

    to_embed = []
    skipped_unchanged = 0
    for n in nodes_with_summary:
        nid = n["id"]
        summary = n["summary"]
        h = hash_summary(summary)
        if not args.rebuild and existing.get(nid) == h:
            skipped_unchanged += 1
            continue
        to_embed.append((nid, n.get("title", ""), summary, h, node_filepath(n)))

    embedded = 0
    if to_embed:
        texts = [t[2] for t in to_embed]
        print(f"Embedding {len(texts)} notes...")
        vectors = model.encode(texts, normalize_embeddings=True,
                               show_progress_bar=len(texts) > 20)
        for (nid, title, summary, h, fp), vec in zip(to_embed, vectors):
            db.execute("""
                INSERT OR REPLACE INTO notes
                (id, title, summary, summary_hash, filepath)
                VALUES (?, ?, ?, ?, ?)
            """, (nid, title, summary, h, fp))
            db.execute("DELETE FROM note_vectors WHERE note_id = ?", (nid,))
            db.execute(
                "INSERT INTO note_vectors (note_id, embedding) VALUES (?, ?)",
                (nid, serialize_embedding(vec)))
            embedded += 1
        db.commit()

    db.close()

    print()
    print(f"  embedded:           {embedded}")
    print(f"  skipped (unchanged):{skipped_unchanged}")
    print(f"  skipped (no summary):{skipped_no_summary}")
    print(f"\nIndex: {DB_PATH}")


if __name__ == "__main__":
    main()
