"""Stage 9 — note_resolver tests.

Tiers:
  L1 — exact match (exists_fn returns True)
  L2 — fuzzy match (top score >= 0.7)
  L3 — ambiguous (0.4 <= top < 0.7)
  L4 — no_match (top < 0.4 or empty results)
  L5 — edge cases (empty query, single hit, ties)
"""

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.storage.note_resolver import resolve_note_ref


# ── helpers ──────────────────────────────────────────────────────────────────

def _exists(known: set[str]):
    return lambda note_id: note_id in known


def _search(hits: list[tuple[str, float, str]]):
    """Return vault_search_fn yielding fixed (note_id, score, title) hits."""
    def _fn(query, top_k):
        return [{"note_id": n, "score": s, "title": t} for n, s, t in hits[:top_k]]
    return _fn


# ── L1: exact ────────────────────────────────────────────────────────────────

def test_exact_match_returns_exact_status():
    result = resolve_note_ref(
        "mastery-trap",
        vault_search_fn=_search([]),
        exists_fn=_exists({"mastery-trap"}),
    )
    assert result["status"] == "exact"
    assert result["note_id"] == "mastery-trap"


def test_exact_match_does_not_call_search():
    calls = []
    def _spy(query, top_k):
        calls.append(query)
        return []
    resolve_note_ref("governance-capital", vault_search_fn=_spy, exists_fn=_exists({"governance-capital"}))
    assert calls == [], "vault_search_fn should not be called on exact match"


def test_exact_match_strips_whitespace():
    result = resolve_note_ref(
        "  mastery-trap  ",
        vault_search_fn=_search([]),
        exists_fn=_exists({"mastery-trap"}),
    )
    assert result["status"] == "exact"


# ── L2: fuzzy ────────────────────────────────────────────────────────────────

def test_fuzzy_high_confidence():
    result = resolve_note_ref(
        "mastery trap",
        vault_search_fn=_search([("mastery-trap", 0.85, "Mastery Trap"), ("schumacher-principle", 0.5, "Schumacher")]),
        exists_fn=_exists(set()),
    )
    assert result["status"] == "fuzzy"
    assert result["note_id"] == "mastery-trap"
    assert result["confidence"] == 0.85


def test_fuzzy_alternatives_excludes_top_hit():
    result = resolve_note_ref(
        "mastery trap",
        vault_search_fn=_search([
            ("mastery-trap", 0.9, "Mastery Trap"),
            ("mastery-loop", 0.75, "Mastery Loop"),
            ("mastery-signal", 0.72, "Mastery Signal"),
        ]),
        exists_fn=_exists(set()),
    )
    alt_ids = [a["note_id"] for a in result["alternatives"]]
    assert "mastery-trap" not in alt_ids
    assert "mastery-loop" in alt_ids


def test_fuzzy_exact_boundary_07():
    result = resolve_note_ref(
        "q",
        vault_search_fn=_search([("note-a", 0.7, "Note A")]),
        exists_fn=_exists(set()),
    )
    assert result["status"] == "fuzzy"


def test_fuzzy_no_alternatives_when_single_hit():
    result = resolve_note_ref(
        "q",
        vault_search_fn=_search([("note-a", 0.8, "Note A")]),
        exists_fn=_exists(set()),
    )
    assert result["status"] == "fuzzy"
    assert result["alternatives"] == []


# ── L3: ambiguous ────────────────────────────────────────────────────────────

def test_ambiguous_returns_candidates():
    result = resolve_note_ref(
        "architectural",
        vault_search_fn=_search([
            ("architectural-restraint", 0.6, "Architectural Restraint"),
            ("architectural-debt", 0.55, "Architectural Debt"),
        ]),
        exists_fn=_exists(set()),
    )
    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2


def test_ambiguous_lower_boundary_04():
    result = resolve_note_ref(
        "q",
        vault_search_fn=_search([("note-x", 0.4, "Note X")]),
        exists_fn=_exists(set()),
    )
    assert result["status"] == "ambiguous"


def test_ambiguous_just_below_fuzzy():
    result = resolve_note_ref(
        "q",
        vault_search_fn=_search([("note-y", 0.699, "Note Y")]),
        exists_fn=_exists(set()),
    )
    assert result["status"] == "ambiguous"


# ── L4: no_match ─────────────────────────────────────────────────────────────

def test_no_match_empty_results():
    result = resolve_note_ref(
        "xyzzy",
        vault_search_fn=_search([]),
        exists_fn=_exists(set()),
    )
    assert result["status"] == "no_match"
    assert result["candidates"] == []


def test_no_match_all_low_scores():
    result = resolve_note_ref(
        "q",
        vault_search_fn=_search([("note-z", 0.2, "Note Z"), ("note-w", 0.1, "Note W")]),
        exists_fn=_exists(set()),
    )
    assert result["status"] == "no_match"
    assert len(result["candidates"]) == 2


def test_no_match_just_below_ambiguous():
    result = resolve_note_ref(
        "q",
        vault_search_fn=_search([("note-a", 0.399, "Note A")]),
        exists_fn=_exists(set()),
    )
    assert result["status"] == "no_match"


# ── L5: edge cases ────────────────────────────────────────────────────────────

def test_candidates_include_score_and_title():
    result = resolve_note_ref(
        "q",
        vault_search_fn=_search([("note-a", 0.5, "Note Alpha")]),
        exists_fn=_exists(set()),
    )
    c = result["candidates"][0]
    assert c["note_id"] == "note-a"
    assert c["score"] == 0.5
    assert c["title"] == "Note Alpha"


def test_exact_takes_priority_over_high_search_score():
    # Even if search would return a high score, exact wins immediately
    result = resolve_note_ref(
        "mastery-trap",
        vault_search_fn=_search([("other-note", 0.99, "Other")]),
        exists_fn=_exists({"mastery-trap"}),
    )
    assert result["status"] == "exact"
    assert result["note_id"] == "mastery-trap"
