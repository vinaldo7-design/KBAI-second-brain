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
_pagerank: dict[str, float] | None = None

# Retrieval modes (Stage 0 item 3 — formalised cognitive routing precursor).
# - standard:   contradicts + mentioned excluded from PPR walk + path attribution
# - sparring:   contradicts allowed; mentioned still excluded
# - exhaustive: deep audit; mentioned edges walked at query time
RETRIEVAL_MODES = ("standard", "sparring", "exhaustive")


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _get_graph() -> VaultGraph:
    """Single VaultGraph cache. Post-2b the constructor preserves every edge;
    query-time options (collapse, include_mentioned) select the view."""
    global _graph
    if _graph is None:
        _graph = VaultGraph.load(str(_GRAPH_PATH))
    return _graph


def _get_pagerank() -> dict[str, float]:
    """PageRank over the default view, normalised 0–1. Cached after first call."""
    global _pagerank
    if _pagerank is None:
        g = _get_graph()
        scores = nx.pagerank(
            g._simple_digraph(collapse=True, include_mentioned=False),
            weight="weight",
        )
        max_pr = max(scores.values()) if scores else 1.0
        _pagerank = {k: v / max_pr for k, v in scores.items()}
    return _pagerank


def _find_note_file(note_id: str, node: dict) -> Path | None:
    """Thin shim over kbai.storage.note_io.find_note_file (Stage 1 dedup)."""
    from kbai.storage.note_io import find_note_file
    return find_note_file(note_id, _vault_root, node)


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
    for source, target, data in g.view(collapse=True, include_mentioned=False).edges(data=True):
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
    """Legacy mode= entry point → kbai.retrieve.assembler (Stage 1.4).
    Signature unchanged; MCP tools and eval runner call this without modification."""
    from kbai.retrieve.assembler import assemble_context as _assemble
    if mode not in RETRIEVAL_MODES:
        mode = "standard"
    return _assemble(
        query=query,
        db_path=_DB_PATH,
        vault_root=_vault_root,
        graph=_get_graph(),
        model=_get_model(),
        mode=mode,
        seed_k=seed_k,
        char_budget=char_budget,
        top_k=50,
        attr_top_n=15,
    )


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


def _retrieve_with_profile(
    query: str,
    profile_id: str,
    seed_k: int = 5,
    top_k: int = 10,
    char_budget: int = 0,
) -> dict:
    """Profile-aware entry point → kbai.retrieve.assembler (Stage 5.5.3).
    Replaces the deleted _assemble_context_with_profile. char_budget=0 keeps
    content=None for council callers; pass char_budget>0 for content-loading callers."""
    from kbai.cognitive_routing import load_profile
    from kbai.retrieve.assembler import assemble_context as _assemble
    profile = load_profile(profile_id)
    return _assemble(
        query=query,
        db_path=_DB_PATH,
        vault_root=_vault_root,
        graph=_get_graph(),
        model=_get_model(),
        profile=profile,
        seed_k=seed_k,
        char_budget=char_budget,
        top_k=top_k,
        attr_top_n=None,
    )


@app.tool()
def cognition_retrieve_as(
    query: str,
    profile_id: str,
    top_k: int = 10,
    seed_k: int = 5,
) -> dict:
    """Profile-aware retrieval. Same query, the lens specified by profile_id.
    Use cognition_list_profiles to see available lenses.
    Note: this is the single-profile version; for multi-profile council see
    council_retrieve."""
    try:
        return _retrieve_with_profile(
            query=query, profile_id=profile_id, seed_k=seed_k, top_k=top_k
        )
    except FileNotFoundError as e:
        return {"error": str(e)}


@app.tool()
def council_retrieve(
    query: str,
    profile_ids: list[str] | None = None,
    top_k: int = 10,
    seed_k: int = 5,
) -> dict:
    """Council Mode (Stage 5.6). Runs the same query through multiple
    cognitive profiles and returns CouncilEvidence — per-profile top-k notes
    plus consensus / unanimous / unique-to overlap analysis.

    Default profiles: explorer, operator, skeptic. Synthesis (the fourth role)
    is Claude reading this evidence via the /council slash command — there is
    no separate synthesis agent.

    Returns a CouncilEvidence dict (see kbai.contracts.CouncilEvidence)."""
    from kbai.contracts import ContextNote
    from kbai.council import run_council

    def _retrieve_fn(q: str, pid: str, k: int) -> list[ContextNote]:
        try:
            out = _retrieve_with_profile(
                query=q, profile_id=pid, seed_k=seed_k, top_k=k,
            )
        except FileNotFoundError:
            return []
        return [ContextNote(**n) for n in out.get("notes", [])][:k]

    evidence = run_council(
        query=query,
        profile_ids=profile_ids,
        top_k=top_k,
        retrieve_fn=_retrieve_fn,
    )

    # Stage 5.6 feedback hook: record the council event so Stage 8 calibration
    # can correlate which profiles surface notes the user later acts on.
    try:
        from kbai.instrumentation import record_council_event
        record_council_event(
            _DB_PATH,
            query=query,
            profiles=evidence.profiles,
            per_profile_top_ids={
                p.profile_id: [n.note_id for n in p.notes]
                for p in evidence.per_profile
            },
        )
    except Exception:
        pass  # never block retrieval on instrumentation

    return evidence.model_dump(by_alias=True)


@app.tool()
def cognition_list_profiles() -> list[dict]:
    """List all cognitive (thinking-fidelity) profiles available in the
    registry. A profile is a retrieval/ranking lens over the same vault
    graph — distinct from voice_profile (which only changes rendering).
    v1 ships functional profiles only: default, skeptic, operator, builder.
    Person-named profiles are calibrated, not declared (see Stage 8)."""
    from kbai.cognitive_routing import list_profiles
    return [p.model_dump() for p in list_profiles()]


@app.tool()
def cognition_get_profile(profile_id: str) -> dict:
    """Fetch a single cognitive profile by id. Returns the full profile
    schema: edge weight overrides, contradiction/mention policies, path
    and abstraction preferences. Used by retrieve_assemble (in a future
    stage) to gate the PPR walk and modify edge weights."""
    from kbai.cognitive_routing import load_profile
    try:
        return load_profile(profile_id).model_dump()
    except FileNotFoundError as e:
        return {"error": str(e)}


@app.tool()
def cognition_compare_profiles(
    query: str,
    profile_ids: list[str],
    top_k: int = 15,
) -> dict:
    """Compare multiple cognitive profiles on the same query. Returns a
    ProfileComparison with per-profile top-k note lists and a divergence_score
    (Jaccard distance over top-k id sets: 0.0=identical, 1.0=disjoint).

    Use /compare-thinkers for a rendered side-by-side view."""
    from kbai.contracts import ContextNote, ProfileComparison

    per_profile: dict[str, list[ContextNote]] = {}
    for pid in profile_ids:
        try:
            out = _retrieve_with_profile(query=query, profile_id=pid, top_k=top_k)
        except FileNotFoundError:
            per_profile[pid] = []
            continue
        per_profile[pid] = [ContextNote(**n) for n in out.get("notes", [])][:top_k]

    # Jaccard distance over the union of top-k note id sets.
    sets = [set(n.note_id for n in notes) for notes in per_profile.values()]
    if len(sets) < 2:
        divergence = 0.0
    else:
        union: set[str] = set().union(*sets)
        intersection: set[str] = sets[0].copy()
        for s in sets[1:]:
            intersection &= s
        divergence = round(
            (len(union) - len(intersection)) / len(union) if union else 0.0, 4
        )

    result = ProfileComparison(
        query=query,
        profiles=list(profile_ids),
        per_profile={pid: notes for pid, notes in per_profile.items()},
        divergence_score=divergence,
        overlap_top_n=top_k,
    )
    return result.model_dump()


_SKIP_DIRS = {".obsidian", ".trash", "Templates", "07-attachments", "__pycache__", ".git"}


@app.tool()
def recent_notes(limit: int = 10, since_ts: float | None = None, topic: str | None = None) -> list[dict]:
    """Return recently modified vault notes, newest first.

    Args:
        limit:    Max notes to return (default 10).
        since_ts: Unix timestamp lower bound (inclusive). None = no lower bound.
        topic:    If set, filter to notes whose filename or first heading contains
                  this string (case-insensitive).
    """
    results = []
    for md_file in _vault_root.rglob("*.md"):
        # Skip system directories
        if any(part in _SKIP_DIRS for part in md_file.parts):
            continue
        try:
            mtime = md_file.stat().st_mtime
        except OSError:
            continue
        if since_ts is not None and mtime < since_ts:
            continue
        note_id = md_file.stem
        if topic and topic.lower() not in note_id.lower():
            continue
        results.append({
            "note_id": note_id,
            "title": note_id.replace("-", " ").title(),
            "modified_ts": mtime,
            "modified_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime)),
            "summary": None,
        })

    results.sort(key=lambda x: x["modified_ts"], reverse=True)
    return results[:limit]


@app.tool()
def imagine(
    seed: str,
    mode: str = "fracture",
    depth: int = 2,
    k: int = 5,
) -> dict:
    """Propose new research domains by reading cluster shape around a seed
    note. Returns an ImaginationEvidence bundle — cluster signature + a
    synthesizer prompt for Claude to consume via the /imagine slash command.

    Reasons over *absence*: what's structurally missing from a cluster.

    Modes (complete compass coverage):
      extend       sideways  — neighbouring domains that continue the direction
      fracture     adversarial — rival traditions attacking load-bearing nodes
      bridge       cross-cluster — distant fields with isomorphic structure
      deepen       downward — mechanisms underneath the abstract claims
      historicise  backward — intellectual lineages implicitly inherited

    Args:
        seed: anchor note_id (or map id)
        mode: one of extend|fracture|bridge|deepen|historicise
        depth: BFS hops (default 2)
        k: number of domains to request (default 5)
    """
    from kbai.imagination import imagine as _imagine
    return _imagine(_get_graph(), seed=seed, mode=mode, depth=depth, k=k)


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
