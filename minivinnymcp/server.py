import hashlib
import os
import sys
import sqlite3
import time
from pathlib import Path

_vault_root = Path(os.environ["VAULT_ROOT"])
sys.path.insert(0, str(_vault_root))

import networkx as nx
import numpy as np
import sqlite_vec
import yaml
from sentence_transformers import SentenceTransformer
from mcp.server.fastmcp import FastMCP

from vault_search import serialize_embedding, QUERY_PREFIX, MODEL_NAME
from vault_graph_loader import VaultGraph

_DB_PATH = _vault_root / "06-Maps" / "vault-embeddings.db"
_GRAPH_PATH = _vault_root / "06-Maps" / "vault-graph.json"
_TAXONOMY_PATH = _vault_root / "vault_taxonomy.yaml"

_model: SentenceTransformer | None = None
_graph: VaultGraph | None = None
_graph_exhaustive: VaultGraph | None = None
_pagerank: dict[str, float] | None = None

# Retrieval modes (Stage 0 item 3 — formalised cognitive routing precursor).
# - standard:   contradicts + mentioned excluded from PPR walk + path attribution
# - sparring:   contradicts allowed; mentioned still excluded
# - exhaustive: deep audit; mentioned edges loaded into graph and walked
RETRIEVAL_MODES = ("standard", "sparring", "exhaustive")


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _get_graph() -> VaultGraph:
    global _graph
    if _graph is None:
        _graph = VaultGraph.load(str(_GRAPH_PATH))
    return _graph


def _get_graph_exhaustive() -> VaultGraph:
    """Loaded with include_mentioned=True. Used only by mode='exhaustive'."""
    global _graph_exhaustive
    if _graph_exhaustive is None:
        _graph_exhaustive = VaultGraph.load(str(_GRAPH_PATH), include_mentioned=True)
    return _graph_exhaustive


def _get_pagerank() -> dict[str, float]:
    """PageRank over the vault graph, normalised 0–1. Cached after first call."""
    global _pagerank
    if _pagerank is None:
        g = _get_graph()
        scores = nx.pagerank(g._simple_digraph(), weight="weight")
        max_pr = max(scores.values()) if scores else 1.0
        _pagerank = {k: v / max_pr for k, v in scores.items()}
    return _pagerank


def _find_note_file(note_id: str, node: dict) -> Path | None:
    """Resolve a note to its filesystem path. Tries node metadata first, then vault scan."""
    for key in ("filepath", "file_path", "path"):
        fp = node.get(key)
        if fp:
            p = _vault_root / fp
            if p.exists():
                return p
    for p in _vault_root.rglob(f"{note_id}.md"):
        return p
    return None


def _record_hits(query: str, results: list[dict], mode: str) -> None:
    """Fire-and-forget: thin shim over kbai.instrumentation.record_note_hits.
    Preserves the legacy note_hits schema; also captures query text into
    query_log so the golden-set sampler can recover queries by hash."""
    from kbai.instrumentation import record_note_hits
    record_note_hits(_DB_PATH, query=query, results=results, mode=mode)


app = FastMCP("mini-vinny")


def _vault_search_impl(query: str, top_k: int = 5) -> list[dict]:
    """Semantic search over vault note summaries."""
    qvec = _get_model().encode(QUERY_PREFIX + query, normalize_embeddings=True)

    db = sqlite3.connect(_DB_PATH)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)

    rows = db.execute(
        """
        SELECT v.note_id, v.distance, n.title, n.summary, n.filepath
        FROM note_vectors v
        JOIN notes n ON n.id = v.note_id
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (serialize_embedding(qvec), top_k),
    ).fetchall()
    db.close()

    return [
        {
            "note_id": nid,
            "score": float(dist),
            "title": title,
            "summary": summary,
            "filepath": fp,
        }
        for nid, dist, title, summary, fp in rows
    ]


@app.tool()
def vault_search(query: str, top_k: int = 5) -> list[dict]:
    """[legacy alias of retrieve_search] Semantic search over vault note summaries."""
    return _vault_search_impl(query, top_k)


@app.tool()
def retrieve_search(query: str, top_k: int = 5) -> list[dict]:
    """Semantic search over vault note summaries."""
    return _vault_search_impl(query, top_k)


@app.tool()
def graph_expand(note_id: str, max_hops: int = 1) -> dict:
    """Typed graph expansion from a note up to max_hops depth. Returns neighbours
    sorted by edge weight descending. Edge weights come from vault_taxonomy.yaml."""
    g = _get_graph()

    if not g.exists(note_id):
        return {"error": f"Note '{note_id}' not found in graph."}

    root_node = g.node(note_id) or {}
    weights = g.taxonomy_weights

    visited: set[str] = {note_id}
    frontier: list[str] = [note_id]
    hops_result: list[dict] = []

    for hop in range(1, max_hops + 1):
        next_frontier: list[str] = []
        for current in frontier:
            for e in g.neighbours(current, direction="both"):
                neighbour = e.target if e.source == current else e.source
                if neighbour in visited:
                    continue
                visited.add(neighbour)
                next_frontier.append(neighbour)
                n_node = g.node(neighbour) or {}
                hops_result.append({
                    "note_id": neighbour,
                    "title": n_node.get("title"),
                    "summary": n_node.get("summary"),
                    "edge_type": e.type,
                    "direction": "out" if e.source == current else "in",
                    "weight": weights.get(e.type, 1.0),
                    "annotation": e.annotation,
                    "hop": hop,
                })
        frontier = next_frontier
        if not frontier:
            break

    hops_result.sort(key=lambda x: -x["weight"])

    return {
        "note_id": note_id,
        "title": root_node.get("title"),
        "summary": root_node.get("summary"),
        "hops": hops_result,
    }


@app.tool()
def audit_taxonomy(check_type: str, against_type: str) -> list[dict]:
    """Score all edges of check_type by cosine similarity to against_type's description.
    Returns a ranked triage list — high scores are strongest retype candidates."""
    g = _get_graph()
    model = _get_model()

    with open(_TAXONOMY_PATH, encoding="utf-8") as f:
        taxonomy = yaml.safe_load(f)

    edge_types = taxonomy.get("edge_types", {})

    if check_type not in edge_types:
        return [{"error": f"check_type '{check_type}' not in taxonomy"}]
    if against_type not in edge_types:
        return [{"error": f"against_type '{against_type}' not in taxonomy"}]

    against_desc = edge_types[against_type].get("description", against_type)
    against_vec = model.encode(against_desc, normalize_embeddings=True)

    results: list[dict] = []
    for source, target, data in g.G.edges(data=True):
        if data.get("type") != check_type:
            continue
        src_node = g.node(source) or {}
        tgt_node = g.node(target) or {}
        annotation = data.get("annotation") or ""
        src_summary = src_node.get("summary") or source
        tgt_summary = tgt_node.get("summary") or target

        parts = [src_summary, annotation, tgt_summary] if annotation else [src_summary, tgt_summary]
        rel_vec = model.encode(" | ".join(parts), normalize_embeddings=True)
        score = float(np.dot(rel_vec, against_vec))

        results.append({
            "source": source,
            "target": target,
            "score": round(score, 4),
            "annotation": annotation or None,
            "source_summary": src_summary,
            "target_summary": tgt_summary,
        })

    results.sort(key=lambda x: -x["score"])
    return results


def _get_note_with_context_impl(note_id: str) -> dict:
    """Read a note's full markdown content plus its typed graph neighbourhood.
    Tier 3 retrieval — use after vault_search or graph_expand have identified a note."""
    g = _get_graph()

    if not g.exists(note_id):
        return {"error": f"Note '{note_id}' not found in graph."}

    node = g.node(note_id) or {}
    note_file = _find_note_file(note_id, node)
    content = note_file.read_text(encoding="utf-8") if note_file else None

    edges = [
        {
            "note_id": e.target if e.source == note_id else e.source,
            "edge_type": e.type,
            "direction": "out" if e.source == note_id else "in",
            "annotation": e.annotation,
        }
        for e in g.neighbours(note_id, direction="both")
    ]

    return {
        "note_id": note_id,
        "title": node.get("title"),
        "summary": node.get("summary"),
        "content": content,
        "edges": edges,
    }


@app.tool()
def get_note_with_context(note_id: str) -> dict:
    """[legacy alias of notes_get_with_context] Read a note + typed neighbourhood."""
    return _get_note_with_context_impl(note_id)


@app.tool()
def notes_get_with_context(note_id: str) -> dict:
    """Read a note's full markdown content plus its typed graph neighbourhood."""
    return _get_note_with_context_impl(note_id)


def _assemble_context_impl(
    query: str,
    seed_k: int = 5,
    char_budget: int = 12000,
    mode: str = "standard",
) -> dict:
    """Full hybrid retrieval pipeline: vector seed → Personalized PageRank over
    typed graph → char budget cap.
    - mode='standard' (default): excludes contradicts + mentioned edges
    - mode='sparring': includes contradicts; excludes mentioned
    - mode='exhaustive': deep audit, allows mentioned edges (low-signal flagged)"""
    if mode not in RETRIEVAL_MODES:
        mode = "standard"
    g = _get_graph_exhaustive() if mode == "exhaustive" else _get_graph()
    model = _get_model()

    # Tier 1: vector seed
    qvec = model.encode(QUERY_PREFIX + query, normalize_embeddings=True)
    db = sqlite3.connect(_DB_PATH)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    rows = db.execute(
        """
        SELECT v.note_id, v.distance, n.title, n.summary, n.filepath
        FROM note_vectors v
        JOIN notes n ON n.id = v.note_id
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (serialize_embedding(qvec), seed_k),
    ).fetchall()
    db.close()

    seed_meta: dict[str, dict] = {}
    seed_scores: dict[str, float] = {}
    for nid, dist, title, summary, fp in rows:
        sim = max(0.0, 1.0 - float(dist))
        seed_scores[nid] = sim
        seed_meta[nid] = {"title": title, "summary": summary, "filepath": fp}

    # Tier 2: PPR over typed graph seeded by dense retrieval scores.
    # Mode-gated edge exclusion (cognitive routing precursor).
    if mode == "standard":
        exclude = {"contradicts", "mentioned"}
    elif mode == "sparring":
        exclude = {"mentioned"}
    else:  # exhaustive
        exclude = set()
    ppr_scores = g.ppr_expand(seed_scores, exclude_types=exclude)

    # Build ranked list: top 50 by PPR score, skip broken nodes
    ranked = sorted(
        ((nid, score) for nid, score in ppr_scores.items() if g.exists(nid)),
        key=lambda x: -x[1],
    )[:50]

    # Char budget: read full content top-down until exhausted
    results: list[dict] = []
    chars_used = 0
    for i, (nid, ppr) in enumerate(ranked):
        node = g.node(nid) or {}
        if nid in seed_meta:
            title = seed_meta[nid]["title"]
            summary = seed_meta[nid]["summary"]
            source = "seed"
        else:
            title = node.get("title")
            summary = node.get("summary")
            source = "ppr"

        note_file = _find_note_file(nid, node)
        content = None
        if note_file and chars_used < char_budget:
            raw = note_file.read_text(encoding="utf-8")
            remaining = char_budget - chars_used
            if len(raw) <= remaining:
                content = raw
                chars_used += len(raw)
            elif i < 3:
                content = raw[:remaining]
                chars_used += remaining

        results.append({
            "note_id": nid,
            "title": title,
            "summary": summary,
            "content": content,
            "composite_score": round(ppr, 4),
            "source": source,
            "via_edge": None,
            "parent": None,
        })

    # Path attribution for top 15 PPR-sourced notes
    seed_ids = list(seed_meta.keys())
    ppr_targets = [r["note_id"] for r in results[:15] if r["source"] == "ppr"]
    if mode == "standard":
        path_exclude = {"contradicts", "referenced-in", "untyped", "mentioned"}
    elif mode == "sparring":
        path_exclude = {"referenced-in", "untyped", "mentioned"}
    else:  # exhaustive — admit mentioned edges; still drop pure-structural noise
        path_exclude = {"referenced-in", "untyped"}
    attributions = g.path_attributions(seed_ids, ppr_targets, exclude_types=path_exclude)
    for r in results:
        r["reasoning_path"] = (
            attributions.get(r["note_id"]) if r["source"] == "ppr" else None
        )

    # Instrumentation: record note hits for future relevance learning
    _record_hits(query, results, mode)

    return {
        "query": query,
        "notes": results,
        "chars_used": chars_used,
        "char_budget": char_budget,
    }


@app.tool()
def assemble_context(
    query: str,
    seed_k: int = 5,
    char_budget: int = 12000,
    mode: str = "standard",
) -> dict:
    """[legacy alias of retrieve_assemble] Full hybrid retrieval pipeline."""
    return _assemble_context_impl(query, seed_k, char_budget, mode)


@app.tool()
def retrieve_assemble(
    query: str,
    seed_k: int = 5,
    char_budget: int = 12000,
    mode: str = "standard",
) -> dict:
    """Full hybrid retrieval pipeline: vector seed → Personalized PageRank over
    typed graph → char budget cap. mode='standard' excludes contradicts edges
    from the PPR walk; mode='sparring' includes them for challenge/counterargument
    queries. Primary synthesis entry point."""
    return _assemble_context_impl(query, seed_k, char_budget, mode)


@app.tool()
def analytics_connect_suggest(categories: list[str] | None = None) -> dict:
    """Read-only link-suggestion analytics over the vault graph. Returns ranked
    candidates per category. Does NOT mutate the vault — apply via Write Agent.
    Categories: orphan_rescue, missing_bidir, tag_cluster_gaps, force_fit_retype,
    low_centrality_high_substance. Pass None for all categories."""
    from kbai.analytics.connect_suggest import connect_suggest
    return connect_suggest(_get_graph(), categories)


if __name__ == "__main__":
    app.run()
