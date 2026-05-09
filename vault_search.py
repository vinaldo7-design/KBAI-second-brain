#!/usr/bin/env python3
"""
vault_search.py — Semantic search over note summaries.

Embeds the query with the same model used by vault_embed.py, returns
the top-K nearest notes by cosine distance. Lower distance = closer match.

Usage:
    python vault_search.py "what have I written about governance"
    python vault_search.py -k 10 "incentive misalignment in AI labs"

Dependencies: pip install sqlite-vec sentence-transformers
"""

import argparse
import sqlite3
import struct
from pathlib import Path

import sqlite_vec
from sentence_transformers import SentenceTransformer

VAULT_ROOT = Path(__file__).parent
DB_PATH = VAULT_ROOT / "06-Maps" / "vault-embeddings.db"
MODEL_NAME = "BAAI/bge-small-en-v1.5"

# BGE models perform better on retrieval when the query is prefixed.
# Documents (summaries) do NOT use the prefix.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def serialize_embedding(vec) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="Query string (in quotes if multi-word)")
    parser.add_argument("-k", type=int, default=5, help="Number of results (default 5)")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"Missing {DB_PATH}. Run vault_embed.py first.")

    model = SentenceTransformer(MODEL_NAME)
    qvec = model.encode(QUERY_PREFIX + args.query, normalize_embeddings=True)

    db = sqlite3.connect(DB_PATH)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)

    rows = db.execute("""
        SELECT v.note_id, v.distance, n.title, n.summary
        FROM note_vectors v
        JOIN notes n ON n.id = v.note_id
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
    """, (serialize_embedding(qvec), args.k)).fetchall()

    db.close()

    print(f"\nQuery: {args.query}\n")
    if not rows:
        print("No results.")
        return

    for i, (nid, dist, title, summary) in enumerate(rows, 1):
        print(f"{i}. [{dist:.3f}] {nid}")
        if title and title != nid:
            print(f"     {title}")
        truncated = summary if len(summary) <= 220 else summary[:217] + "..."
        print(f"     {truncated}")
        print()


if __name__ == "__main__":
    main()
