"""Stage 9 — fuzzy note resolution.

Four-tier resolution:
  exact     — query matches a known note_id literally
  fuzzy     — top score >= 0.7 (auto-pick, alternatives surfaced)
  ambiguous — 0.4 <= top < 0.7 (force user to choose)
  no_match  — top < 0.4

Usage:
    result = resolve_note_ref(
        query,
        vault_search_fn=lambda q, top_k: [{"note_id": ..., "score": ..., "title": ...}, ...],
        exists_fn=lambda note_id: True/False,
    )
"""

from __future__ import annotations

from typing import Callable


def resolve_note_ref(
    query: str,
    vault_search_fn: Callable[[str, int], list[dict]],
    exists_fn: Callable[[str], bool],
) -> dict:
    query = query.strip()

    # Tier 1 — exact match
    if exists_fn(query):
        return {"status": "exact", "note_id": query}

    # Tiers 2-4 — delegate to vault search
    hits = vault_search_fn(query, 5)
    if not hits:
        return {"status": "no_match", "candidates": []}

    top = hits[0]
    top_score = top.get("score", 0.0)
    candidates = [
        {"note_id": h.get("note_id", ""), "score": h.get("score", 0.0), "title": h.get("title", "")}
        for h in hits
    ]

    if top_score >= 0.7:
        return {
            "status": "fuzzy",
            "note_id": top.get("note_id", ""),
            "confidence": top_score,
            "alternatives": candidates[1:],
        }
    elif top_score >= 0.4:
        return {"status": "ambiguous", "candidates": candidates}
    else:
        return {"status": "no_match", "candidates": candidates}
