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
import json
from pathlib import Path

# Single source of truth for the per-note embed logic, the model name, and the
# (de)serialisation helpers. embed_note is reused by the on-write reindex hook,
# so the batch builder and the write path can never drift. MODEL_NAME /
# serialize_embedding ultimately come from vault_search via kbai.embed.indexer.
from kbai.embed.indexer import (
    EMBED_DIM,
    MODEL_NAME,
    embed_note,
    get_model,
    hash_summary,
    init_db,
    open_db,
    serialize_embedding,
)

VAULT_ROOT = Path(__file__).parent
GRAPH_JSON = VAULT_ROOT / "06-Maps" / "vault-graph.json"
DB_PATH = VAULT_ROOT / "06-Maps" / "vault-embeddings.db"


def node_filepath(node: dict) -> str:
    """Return a graph node's vault-relative path.

    vault_graph.py serialises Node dataclasses (via asdict), which store the
    path under the key ``path``. Older/alternate dumps may use ``filepath``;
    fall back to that for safety. Returns "" if neither is present.
    """
    return node.get("path") or node.get("filepath", "") or ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true",
                        help="Re-embed every note regardless of hash")
    args = parser.parse_args()

    if not GRAPH_JSON.exists():
        raise SystemExit(f"Missing {GRAPH_JSON}. Run vault_graph.py first.")

    data = json.loads(GRAPH_JSON.read_text())
    # Only embed notes whose summary is a non-empty STRING. Defensive: a node whose
    # summary parsed as a dict/None (e.g. a stray non-note file) is skipped, not crashed on.
    nodes_with_summary = [
        n for n in data["nodes"]
        if isinstance(n.get("summary"), str) and n["summary"].strip()
    ]
    skipped_no_summary = len(data["nodes"]) - len(nodes_with_summary)

    print(f"Loading model {MODEL_NAME} (first run downloads ~33MB)...")
    model = get_model()

    # One shared connection + preloaded model reused across every embed_note
    # call (init_db / open_db now live in kbai.embed.indexer).
    db = open_db(DB_PATH)
    init_db(db)

    existing = {row[0]: row[1] for row in db.execute(
        "SELECT id, summary_hash FROM notes")}

    # Decide up front what needs work so the unchanged-skip count and the
    # --rebuild force-path stay identical to the previous behaviour.
    to_embed = []
    skipped_unchanged = 0
    for n in nodes_with_summary:
        nid = n["id"]
        summary = n["summary"]
        h = hash_summary(summary)
        if not args.rebuild and existing.get(nid) == h:
            skipped_unchanged += 1
            continue
        to_embed.append((nid, n.get("title", ""), summary, n))

    embedded = 0
    if to_embed:
        print(f"Embedding {len(to_embed)} notes...")
        for nid, title, summary, n in to_embed:
            # --rebuild: clear the existing row so embed_note's hash-skip can't
            # short-circuit a forced re-embed of an unchanged summary.
            if args.rebuild:
                db.execute("DELETE FROM notes WHERE id = ?", (nid,))
                db.execute("DELETE FROM note_vectors WHERE note_id = ?", (nid,))
            if embed_note(
                nid,
                summary,
                DB_PATH,
                title=title,
                filepath=node_filepath(n),
                model=model,
                db=db,
            ):
                embedded += 1

    db.close()

    print()
    print(f"  embedded:           {embedded}")
    print(f"  skipped (unchanged):{skipped_unchanged}")
    print(f"  skipped (no summary):{skipped_no_summary}")
    print(f"\nIndex: {DB_PATH}")


if __name__ == "__main__":
    main()
