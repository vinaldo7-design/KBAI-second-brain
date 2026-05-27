"""perplexity-mcp — Perplexity Deep Research as an annotator for the vault.

Four tools (Stage 4 — research split):
  research_note          — single-note deep research (no writes)
  research_cluster       — cluster-level cross-cutting research (no writes)
  research_verify_claim  — narrow fact-check on a specific claim text
  apply_research         — append findings to the note as a clearly-marked section

Discipline: never silently rewrites existing prose. All Perplexity-derived
content lives under "## External research (Perplexity, YYYY-MM-DD)".
"""

import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from hashlib import md5
from pathlib import Path
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

_VAULT_ROOT = Path(os.environ["VAULT_ROOT"])
_GRAPH_PATH = _VAULT_ROOT / "06-Maps" / "vault-graph.json"
_LOG_DB = _VAULT_ROOT / "06-Maps" / "perplexity-research.db"

_API_URL = "https://api.perplexity.ai/chat/completions"
_MODEL = os.environ.get("PERPLEXITY_MODEL", "sonar-deep-research")
_TIMEOUT = int(os.environ.get("PERPLEXITY_TIMEOUT", "300"))

_CLUSTER_SYSTEM_PROMPT_PREFIX = (
    "You are researching a CLUSTER of related notes from a personal knowledge base. "
    "Surface cross-cutting themes, contradictions between notes, and external sources "
    "relevant to the cluster as a whole — not to any single note.\n\n"
)

_VERIFY_SCHEMA_INSTRUCTION = (
    "Return STRICT JSON with exactly these fields:\n"
    '{"verdict": "...", "confidence": 0.0, "evidence": [{"url": "...", "note": "..."}]}\n'
    "verdict must be one of: supports, contradicts, mixed, uncertain.\n"
    "confidence must be a float in [0, 1].\n"
    "evidence is a list of objects with url and note fields.\n"
    "Do not include any extra keys or commentary."
)

_JSON_SCHEMA_INSTRUCTION = """Return your findings as STRICT JSON in exactly this shape:

{
  "sources": [
    { "title": string, "url": string, "summary": string, "published": string|null }
  ],
  "claim_checks": [
    {
      "claim_snippet": string,
      "verdict": "supports"|"contradicts"|"mixed"|"uncertain",
      "evidence": [ { "url": string, "note": string } ]
    }
  ],
  "cross_links": [
    { "hint_text": string, "reason": string }
  ],
  "open_questions": [
    { "question": string, "reason": string }
  ],
  "raw_summary": string
}

Do not include any extra keys or commentary. The top-level value MUST be an object with exactly these fields."""


# --- Note resolution ------------------------------------------------------

def _find_note_file(note_id: str) -> Path | None:
    """Thin shim over kbai.storage.note_io.find_note_file (Stage 1 dedup)."""
    import sys
    sys.path.insert(0, str(_VAULT_ROOT))
    from kbai.storage.note_io import find_note_file
    return find_note_file(note_id, _VAULT_ROOT)


def _load_graph() -> dict | None:
    if not _GRAPH_PATH.exists():
        return None
    with open(_GRAPH_PATH, encoding="utf-8") as f:
        return json.load(f)


def _cluster_expand(map_id: str, cluster_hops: int) -> list[str]:
    """BFS over the vault graph JSON from map_id up to cluster_hops.
    Returns neighbour note_ids ordered by hop distance (nearest first),
    map_id itself excluded."""
    graph = _load_graph()
    if not graph:
        return []

    adj: dict[str, list[str]] = {}
    for e in graph.get("edges", []):
        if not e.get("target_exists", True):
            continue
        src, tgt = e.get("source", ""), e.get("target", "")
        if src and tgt:
            adj.setdefault(src, []).append(tgt)
            adj.setdefault(tgt, []).append(src)

    visited: set[str] = {map_id}
    frontier = [map_id]
    result: list[str] = []
    for _ in range(cluster_hops):
        next_frontier: list[str] = []
        for nid in frontier:
            for neighbour in adj.get(nid, []):
                if neighbour not in visited:
                    visited.add(neighbour)
                    next_frontier.append(neighbour)
                    result.append(neighbour)
        frontier = next_frontier
        if not frontier:
            break
    return result


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _match_vault_note(hint_text: str, graph: dict | None) -> str | None:
    """Fuzzy match a hint to an existing vault note by title or normalised id."""
    if not graph:
        return None
    target = _normalize(hint_text)
    if not target:
        return None
    nodes = graph.get("nodes", [])
    for n in nodes:
        if _normalize(n.get("id", "")) == target:
            return n["id"]
    for n in nodes:
        title = n.get("title") or ""
        if _normalize(title) == target:
            return n["id"]
    for n in nodes:
        title_norm = _normalize(n.get("title") or "")
        if title_norm and (target in title_norm or title_norm in target):
            return n["id"]
    return None


# --- Perplexity call ------------------------------------------------------

def _call_perplexity_raw(system_prompt: str, user_content: str) -> str:
    """Core Perplexity caller. Returns raw response content string.
    Raises RuntimeError on any failure (network, status, parse)."""
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        raise RuntimeError("PERPLEXITY_API_KEY not set in environment.")

    payload = {
        "model": _MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(_API_URL, json=payload, headers=headers, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise RuntimeError(f"Perplexity request failed: {e}") from e

    if resp.status_code != 200:
        raise RuntimeError(f"Perplexity returned {resp.status_code}: {resp.text[:500]}")

    try:
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except (KeyError, ValueError) as e:
        raise RuntimeError(f"Unexpected Perplexity response shape: {e}") from e


def _call_perplexity(note_content: str) -> dict:
    """Single-note research. Wraps _call_perplexity_raw with the default research prompt."""
    system_prompt = (
        "You are a research agent helping update a personal knowledge note. "
        "The note content will be provided by the user.\n\n"
        "1. Find recent, high-quality sources (papers, articles, docs) directly relevant to the note.\n"
        "2. Check whether the core claims still hold according to current literature.\n"
        "3. Suggest cross-references or related concepts that should be linked.\n"
        "4. Surface open questions the note doesn't address.\n\n"
        + _JSON_SCHEMA_INSTRUCTION
    )
    raw = _call_perplexity_raw(system_prompt, f"Note content:\n\n{note_content}")
    return _extract_json(raw)


def _extract_json(content: str) -> dict:
    """Parse JSON from Perplexity output. Tolerates ```json fences and surrounding prose."""
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1)
    else:
        first = content.find("{")
        last = content.rfind("}")
        if first == -1 or last == -1 or last <= first:
            raise RuntimeError("No JSON object found in Perplexity response.")
        candidate = content[first : last + 1]

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse Perplexity JSON: {e}") from e

    for key in ("sources", "claim_checks", "cross_links", "open_questions"):
        parsed.setdefault(key, [])
    parsed.setdefault("raw_summary", "")
    return parsed


# --- Logging sidecar ------------------------------------------------------

def _log_research(note_id: str, researched_at: str, content_hash: str) -> None:
    """Track when each note was last refreshed. Best-effort, never raises."""
    try:
        db = sqlite3.connect(_LOG_DB)
        db.execute(
            """CREATE TABLE IF NOT EXISTS research_log (
                note_id       TEXT,
                researched_at TEXT,
                content_hash  TEXT,
                model         TEXT
            )"""
        )
        db.execute(
            "INSERT INTO research_log VALUES (?,?,?,?)",
            (note_id, researched_at, content_hash, _MODEL),
        )
        db.commit()
        db.close()
    except Exception:
        pass


def _log_claim_verify(claim_hash: str, verdict: str, confidence: float) -> None:
    """Best-effort: record claim verification results for Stage 8 calibration."""
    try:
        db = sqlite3.connect(_LOG_DB)
        db.execute(
            """CREATE TABLE IF NOT EXISTS claim_checks (
                claim_hash TEXT,
                verdict    TEXT,
                confidence REAL,
                model      TEXT,
                ts         INTEGER
            )"""
        )
        db.execute(
            "INSERT INTO claim_checks VALUES (?,?,?,?,?)",
            (claim_hash, verdict, float(confidence), _MODEL, int(time.time())),
        )
        db.commit()
        db.close()
    except Exception:
        pass


# --- MCP server -----------------------------------------------------------

app = FastMCP("perplexity-research")


@app.tool()
def research_note(note_id: str, mode: str = "single", cluster_hops: int = 1) -> dict:
    """Call Perplexity Deep Research on a vault note. Returns structured findings
    with sources, claim_checks, cross_links, open_questions. Does NOT modify
    the note — use apply_research to patch findings in. mode='cluster' is
    reserved for future expansion; currently behaves like 'single'."""
    note_file = _find_note_file(note_id)
    if not note_file:
        return {"error": f"Note '{note_id}' not found under {_VAULT_ROOT}"}

    note_content = note_file.read_text(encoding="utf-8")

    try:
        payload = _call_perplexity(note_content)
    except RuntimeError as e:
        return {"error": str(e)}

    graph = _load_graph()
    for cl in payload.get("cross_links") or []:
        hint = cl.get("hint_text") or ""
        match = _match_vault_note(hint, graph)
        if match:
            cl["vault_note_id"] = match

    researched_at = datetime.now(timezone.utc).isoformat()
    content_hash = md5(note_content.encode("utf-8")).hexdigest()[:12]
    _log_research(note_id, researched_at, content_hash)

    return {
        "note_id": note_id,
        "researched_at": researched_at,
        "model": _MODEL,
        "sources": payload.get("sources") or [],
        "claim_checks": payload.get("claim_checks") or [],
        "cross_links": payload.get("cross_links") or [],
        "open_questions": payload.get("open_questions") or [],
        "raw_summary": payload.get("raw_summary") or "",
    }


@app.tool()
def apply_research(
    note_id: str,
    sources: list[dict] | None = None,
    claim_checks: list[dict] | None = None,
    cross_links: list[dict] | None = None,
    open_questions: list[dict] | None = None,
    raw_summary: str = "",
    include_raw_summary: bool = True,
    researched_at: str | None = None,
) -> dict:
    """Append research findings to a note. Delegates to the single journalled
    writer in kbai/storage/research_appender.py — never touches write_text
    directly. Idempotent per UTC day."""
    import sys
    sys.path.insert(0, str(_VAULT_ROOT))
    from kbai.storage.research_appender import append_research_section

    payload = {
        "note_id": note_id,
        "sources": sources or [],
        "claim_checks": claim_checks or [],
        "cross_links": cross_links or [],
        "open_questions": open_questions or [],
        # include_raw_summary=False suppresses the summary section by passing
        # an empty raw_summary; the appender skips empty summaries.
        "raw_summary": raw_summary if include_raw_summary else "",
        "researched_at": researched_at,
    }
    return append_research_section(_VAULT_ROOT, note_id, payload).model_dump()


@app.tool()
def research_cluster(map_id: str, cluster_hops: int = 1) -> dict:
    """Call Perplexity Deep Research on a cluster of related notes anchored at
    map_id. Surfaces cross-cutting themes, contradictions between notes, and
    external sources relevant to the cluster as a whole — not to any single note.

    Returns the same ResearchPayload shape as research_note, plus a
    `cluster_notes` list of note_ids included in the cluster."""
    cluster_ids = _cluster_expand(map_id, cluster_hops)
    if not cluster_ids:
        return {"error": f"Note '{map_id}' not found in graph or has no neighbours."}

    # Priority-order: root note first, then cluster members; truncate to 12k total.
    note_ids_ordered = [map_id] + cluster_ids
    chunks: list[str] = []
    total_chars = 0
    included: list[str] = []
    for nid in note_ids_ordered:
        if total_chars >= 12000:
            break
        nf = _find_note_file(nid)
        if not nf:
            continue
        text = nf.read_text(encoding="utf-8")
        remaining = 12000 - total_chars
        chunk = text[:remaining] if len(text) > remaining else text
        chunks.append(f"--- Note: {nid} ---\n{chunk}")
        total_chars += len(chunk)
        included.append(nid)

    if not chunks:
        return {"error": f"No readable note files found for cluster anchored at '{map_id}'."}

    cluster_content = "\n\n".join(chunks)
    system_prompt = (
        _CLUSTER_SYSTEM_PROMPT_PREFIX + _JSON_SCHEMA_INSTRUCTION
    )

    try:
        raw = _call_perplexity_raw(system_prompt, f"Cluster content:\n\n{cluster_content}")
        payload = _extract_json(raw)
    except RuntimeError as e:
        return {"error": str(e)}

    graph = _load_graph()
    for cl in payload.get("cross_links") or []:
        hint = cl.get("hint_text") or ""
        match = _match_vault_note(hint, graph)
        if match:
            cl["vault_note_id"] = match

    researched_at = datetime.now(timezone.utc).isoformat()
    content_hash = md5(cluster_content.encode("utf-8")).hexdigest()[:12]
    _log_research(map_id, researched_at, content_hash)

    return {
        "note_id": map_id,
        "cluster_notes": included,
        "researched_at": researched_at,
        "model": _MODEL,
        "sources": payload.get("sources") or [],
        "claim_checks": payload.get("claim_checks") or [],
        "cross_links": payload.get("cross_links") or [],
        "open_questions": payload.get("open_questions") or [],
        "raw_summary": payload.get("raw_summary") or "",
    }


@app.tool()
def research_verify_claim(claim_text: str, context: str = "") -> dict:
    """Narrow Perplexity fact-check on a specific claim. Returns a structured
    verdict with confidence and supporting/contradicting evidence.

    verdict ∈ {supports, contradicts, mixed, uncertain}
    confidence ∈ [0, 1]"""
    user_content = (
        f"Claim: {claim_text}"
        + (f"\n\nContext: {context}" if context.strip() else "")
    )
    system_prompt = (
        "Evaluate whether the following claim is supported by current literature. "
        "Be precise and cite specific sources.\n\n"
        + _VERIFY_SCHEMA_INSTRUCTION
    )

    try:
        raw = _call_perplexity_raw(system_prompt, user_content)
        payload = _extract_json(raw)
    except RuntimeError as e:
        return {"error": str(e)}

    verdict = payload.get("verdict", "uncertain")
    if verdict not in ("supports", "contradicts", "mixed", "uncertain"):
        verdict = "uncertain"
    confidence = float(payload.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))
    evidence = payload.get("evidence") or []

    claim_hash = md5(claim_text.encode("utf-8")).hexdigest()[:12]
    _log_claim_verify(claim_hash, verdict, confidence)

    return {
        "claim": claim_text,
        "verdict": verdict,
        "confidence": confidence,
        "evidence": evidence,
    }


if __name__ == "__main__":
    app.run()
